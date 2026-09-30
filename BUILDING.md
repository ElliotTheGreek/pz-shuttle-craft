# Building aboard

The working guide to what a player may build, place and move aboard the
shuttle's cabin, the U.S.S. Adirondack and the field station, and how the
mod's own builders leave it alone. Asked for by the author on 2026-09-27:
"the player [should be] clear to build and customize".

**Not seen in game yet.** Section 4 is what to check.

---

## 1. What a player gets

- **Build anything vanilla lets you build**, on any deck square aboard all
  three: crafted furniture, placed moveables, containers. It stays.
- **Pick up and move the mod's own furniture** the way vanilla furniture is
  moved: beds, bunks, desks, chairs, tables, lockers, counters, shelves,
  crates, consoles, plants, lights, paintings. Where you put it, it stays;
  where you took it from, it stays empty.
- **What cannot be moved**: the replicators, the warp cores, the Doctor's
  stations, the lift panels, the Jefferies tube hatches, and the field
  station's breaker box and its panel. Each works because of where it stands
  (`A.machines`, `FS.spot`): moved, it would be scenery that looks like a
  machine, and the builder would stand a second one where it was.
- **The hull always comes back**: walls, doors and floors are put back by the
  next refit if anything takes them away. A hole in a bulkhead is a hole into
  the void.

## 2. How the builders leave it alone

Three builders place things aboard: the cabin's (`TREK_Build`), the decks'
(`TREK_AdirondackServer.buildDeck`, for the Adirondack and the station) and
the tubes' (`buildTube`, every second while anybody is aboard). All three
used to do two things that fought a player:

1. **Strip anything untagged.** The mod tags everything it places, and the
   builders took an untagged object on the ships' own squares for wilderness
   grown in an unmapped cell. Wilderness grows on the ground, never on a
   deck four storeys up: an untagged object there is something a player
   built. The builders now strip only what `U.isWild` says the engine grew:
   trees, bushes, grass, natural ground.
2. **Put back anything missing.** A fitting picked up to be moved was
   missing from its square, so the next build put a new one there: one in
   the player's hands, one on the square. Now each builder keeps a record of
   what it has placed (`U.madeRecord`: `TREK_Adirondack`'s `made<k>` and
   `madeTube<t>`, `TREK_CabinMade`'s `cabin`), keyed by square and sprite. A
   fitting it placed once and cannot find is the player's, and is not put
   back. The hull is exempt: walls and doors are always put back.

Two details that keep that honest:

- **A refit that takes a fitting away itself clears its record**, so a
  locker replaced to repair it (a container with no store, a door not in the
  special-objects list) is put straight back.
- **`TREK_Rebuild()` clears the cabin's record**: it wipes the cabin whole, the
  player's things with it, and puts every fitting back. The one operation
  that does.

**An existing save** has no record yet. Its first refit after this puts back
whatever is missing (the old behaviour, once) and records everything; from
then on what the player takes stays taken.

## 3. Where it lives

| | |
|---|---|
| `U.isWild`, `U.madeRecord` | `shared/TREK/TREK_Util.lua` |
| The decks' and tubes' record, `fit` | `server/TREK/TREK_AdirondackServer.lua` |
| The cabin's record, `clearSquare(sq, keepBuilt)` | `server/TREK/TREK_Build.lua` |
| Which pieces cannot be picked up (`FIXED`) | `tools/gen_adirondack_pack.py`; the cabin's are vanilla tiles and move as vanilla's do |
| Tests | `tests/test_multiplayer.py`, `building()`; `tests/test_assets.py` checks `FIXED` |

Seven mutations, one at a time, all caught.

## 4. Not yet seen in game

1. Build a piece of carpentry in the cabin, on the Adirondack and in the
   station. Does vanilla let you at all up there? (The squares have floors
   and are in no safehouse; nothing else is known to refuse.)
2. Pick up a bed on the Adirondack and put it down in another room. Leave the
   deck and come back: one bed, where you put it.
3. Try to pick up a replicator: no option.
4. Take a crate out of a hideout: it stays gone.
