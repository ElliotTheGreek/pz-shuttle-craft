# Jefferies tubes, space, and the fear of lifts

Built 2026-09-26. The working guide to the crawlways between the
U.S.S. Adirondack's decks, the hideouts off them, the starfield under her, and
the Turbolift Phobia trait that makes the tubes worth having. `ADIRONDACK.md`
is how the ship is put together; this file is the part of her you crawl.

**Nothing here has been seen in game yet.** Section 7 is what to check first.

---

## 1. What a player gets

- **Every deck is joined to the next by a tube** you crawl through, from end
  to end, across the black between the decks, over the stars. Nobody is moved;
  there is no ladder, no teleport, no menu. You walk up to a hatch in the
  corridor's west wall and it opens, and you crawl.
- **Two hatches per corridor**, both on the west wall beside the lift: the one
  at row 3 goes on to the next deck (Deck 1 to Deck 2 and so on), the one at
  row 5 comes in from the one before. Deck 1 has only the first; Deck 5 only
  the second.
- **Inside a tube you crawl**: vanilla's own crawl animation, at a sneak, and
  no running. Out of it you stand up, and you are sneaking only if you were
  when you went in.
- **Three hideouts**, off tubes 1-2, 3-4 and 4-5: a two-square side crawl, a
  hatch, and a small room where the off-watch crew drink. Two crates and a
  shelf of the good stuff (Romulan ale, whiskey, bloodwine...), a table, two
  chairs, a light, and the empties and the cards they left lying about. You
  stand up in a hideout.
- **Turbolift Phobia**, a negative trait (+2 points): every lift ride is
  instant dread -- stress, panic and misery -- and the lift's menu says so
  before you choose. The tubes cost the phobic nothing.
- **Space outside is space**: black, with stars four storeys down, instead of
  the grass and trees the engine was growing there.

## 2. How the tubes are shaped

`tools/gen_adirondack_tubes.py`, called by `gen_adirondack_lua.py`:

```
deck k corridor (0,3) --hatch--> (-1,3) north past the lift car to row -3
  -> east above the decks: straight runs of 5-13, turns of 2-5 north or south,
     kept in rows -13..-3
  -> at x = pitch-4, south to row 5, east to pitch-1
  --hatch--> deck k+1 corridor (0,5)
```

Every tube is in the frame of the deck it leaves from: `x` runs on past that
deck's east edge into the gap. Each tube has its own seed (`1701 + 37n`), so
a regeneration builds exactly the same tube -- which matters, because a save
must never find a tube moved under it. The four tubes are 159, 169, 165 and
173 squares.

**The walls come from the same rule as the decks'**: a wall on every edge
between a tube square and anything that is not the tube. That is the whole
reason a route may never touch itself: two squares of one tube that share an
edge without being neighbours along it get no wall between them, and the
crawlway opens sideways into its own next leg. `check()` refuses that, two
tubes that touch, and a tube over a deck's room; `tests/test_assets.py`
proves the refusal is there. Where a tube runs beside a deck's own wall (up
the side of the lift car), the deck's wall serves both.

A tube wall that stands on a square outside the tube gets an invisible floor
(`invisible_01_0`) under it, because a wall on a square with no floor behaves
badly; the tube's own squares get the grating (`trek_adirondack_01_26`).

**The hatches are the decks'**: they stand on the corridor squares, so
`gen_adirondack_tubes.build` swaps each deck's plain corridor wall there for a
doorway and a hatch (`01_36`, a door the door service opens like any other).
The hideout's hatch is the tube's own (`01_37`, north-facing).

## 3. How they are built

The server, `TREK_AdirondackServer.lua`:

- **A tube is never built whole.** No player ever has a hundred and sixty
  squares loaded. `AS.serviceTubes` runs every 30 ticks while anybody is
  aboard, and builds whatever of each tube touching their deck is loaded and
  missing -- far ahead of anybody crawling, since the engine loads 76 squares
  round a player. `AS.buildTube(t)` is idempotent and partial by design.
- **A deck's own pass never touches a tube's square** (`A.tubeOwns`), or it
  would take the tube's walls for strays and strip them.
- **The hideout clutter is placed once, ever**, item by item as its square
  loads (`AS.state().clutter`). Taken, it stays taken.
- If a crawler ever does reach a square before its floor, the client's arrival
  hold catches them exactly as it does on a deck: held on the spot, the server
  asked, released when the floor is there.

`TREK_Adirondack.lua` indexes every tube square (`A.tubeIndex`), and:

- `A.locate` answers a tube square with the deck the tube leaves from, so
  everything keyed on "which deck" -- her power, the lamps, the rescue -- just
  works.
- `A.inside` is true on a tube square, so the rescue that puts back somebody
  who has climbed over a wall does not put back somebody crawling.
- `A.crawling` is true on a crawlway and false in a hideout.

## 4. The crawl

`TREK_AdirondackClient.lua`, `AC.serviceCrawl`, on every update of the
client's **own** character (the only one a client may touch):

- on a crawlway: `setVariable("TrekCrawl", true)`, sneaking on, running and
  sprinting off -- every tick, so a held run key changes nothing;
- off it: the variable off, and sneaking put back as it was before the tube.

The animation is two mod AnimSets nodes, `media/AnimSets/player/movement/
trekCrawl.xml` and `idle/trekCrawlIdle.xml`, both playing vanilla's
**`Bob_Crawl`** -- a clip vanilla ships and no vanilla state plays -- when
`TrekCrawl` is true. Two engine facts decided them:

- `AnimNode.compareSelectionConditions` ranks candidate nodes by
  `m_ConditionPriority` first and the number of conditions second. Vanilla's
  highest priority anywhere is 10; ours is 20, so the crawl wins over sneaking,
  a weapon in hand or a limp without having to list them.
- `AnimState.Parse` merges every mod's files in a state's folder
  (`ZomboidFileSystem.resolveAllFiles`), so adding a node is adding a file.

**Neither clip has root motion** (`Dummy01`'s translation is zero in both
`Bob_Crawl` and `Bob_WalkSneak`), so how fast a crawler goes is the sneak's
speed, not the clip's; the clip is only the picture. The idle node holds the
clip at speed 0 so somebody who stops in a tube stays down.

## 5. Space

`tools/gen_void_map.py` writes the mod's map: 28 cells round the cabin and
the Adirondack. Every square within 110 of either ship (and her tubes,
`L.span`) is one of sixteen star-field floors (`trek_adirondack_01_48..63`,
drawn by `gen_adirondack_tiles.py` in screen space so a star is round, not
squashed onto the ground plane); everything further out is an empty square,
which the engine draws as black. A mapped cell is never generated, so no
grass, trees or zombies.

**It lives in `TrekShuttle/common/media/maps/`, and that is the whole fix.**
`MapGroups.createGroups` (bci 60-90) looks for `<common>/media/maps` first
and, when that folder is missing, goes straight on to the next mod without
looking in the version folder at all. The map sat in `42/media/maps` for every
release before this one and **no single-player game ever loaded it**: every
save's `mods.txt` says `maps { }`, and the mod's own log said so every session
(`the 'TrekShuttle' map is not loaded`). The grass was never a clearing
problem.

`U.clearSquare` never strips a star floor (`U.isSpace`), because every
clearing pass under the ships strips the ground.

**The decks are 108 squares apart** (`DECK_PITCH`), because the engine loads
at most 19 chunks of 8 round a player (`IsoChunkMap.CalcChunkWidth`, capped
at 19) -- 79 squares from the edge of their chunk -- and draws nothing it has
not loaded. At 32 the next deck was twelve squares away and in plain view at
any zoom; at 108 the gap is 88, and no deck is ever loaded from another.

## 6. Turbolift Phobia

`trek:turboliftphobia`, cost -2 (points back), in `registries.lua` and
`scripts/trek_traits.txt`. The server's move handler calls
`TraitsServer.onLift` for every granted `turbolift` move, which adds
`C.LiftPhobiaStress`, `C.LiftPhobiaPanic` and `C.LiftPhobiaUnhappy` through
`T.adjust` (server and owning client both, as every trait effect does). The
lift's submenu carries `IGUI_TREK_LiftPhobiaWarn` for the phobic. The icon is
a Gemini raw, `design/art/traits/turboliftphobia_raw.jpg`, through
`tools/gen_trait_icons.py`.

## 7. Not yet seen in game, in the order worth checking

**Needs a new world**: the void map only fills cells the world has never
generated, and every save made before this has grass in them.

1. **Space.** Beam up: black and stars round the shuttle's cabin and the
   Adirondack, at every zoom. The server log should say `void map
   'TrekShuttle' is loaded`. Then the question only the game can answer: how
   the stars look at night -- a floor is lit like any other outdoor square, so
   they may dim after dark.
2. **Spacing.** At the widest zoom on any deck, no other deck in view.
3. **The hatch.** Walk up to the west wall of Deck 1's corridor, row 3: it
   opens. The hatch art is `tube_hatch_raw.jpg` in a full-height door frame.
4. **The crawl.** Into the tube: does `Bob_Crawl` play, which way does it
   face, and does the idle node hold a pose or snap to the T-pose. If the
   crawl reads wrong, the two XML files are all there is to change.
5. **The crossing.** All the way to Deck 2. Watch for being held on a square
   (a floor not yet built) and for anything drawn where a tube should be.
6. **A hideout**, off tube 1-2 about three-quarters of the way along: the side
   crawl, the hatch, standing up, the crates, the empties on the floor.
7. **The phobia.** A new character with Turbolift Phobia: the lift's menu
   warns, a ride brings the panic moodle, and a crawl does not.

## 8. How to change it

```sh
python tools/gen_adirondack_tiles.py     # the tube's walls, grating, hatch; the stars
python tools/gen_adirondack_pack.py
python tools/compose_adirondack.py
python tools/gen_adirondack_lua.py       # the tubes, via gen_adirondack_tubes.py
python tools/gen_void_map.py             # after anything that moves the ship or her tubes
python tools/preview_tubes.py            # design/art/adirondack/tubes/: overview, one render per tube
```

- **A different route**: the constants at the top of
  `gen_adirondack_tubes.py` -- `BAND`, `RUN`, `JOG` -- or a tube's seed. The
  guard will refuse anything that would build without its walls.
- **More or fewer hideouts**: `HIDEOUTS`. What they hold: `A.Stock.stash_*`
  and `A.stockItems("stash")` in `TREK_Adirondack.lua`; what lies on the
  floor: `hideout()`'s `clutter`.
- **A slower or faster crawl**: the crawl is sneak speed. The clip's playback
  is `m_SpeedScale` in `trekCrawl.xml`.
- **Every change to the layout moves `L.rev`**, which rebuilds each deck in an
  existing save on the next visit.

## 9. What would have bitten you

- **A door found by its sprite is a door found only while it is shut.**
  `ToggleDoor` swaps an open door's picture for the one two along. The tube
  builder runs every 30 ticks and put a second hatch into every open one; the
  deck builder took an open door for a stray and replaced it with a shut one.
  Both now look for *our door on that edge* (`ourDoor`, `entryFor`), and the
  test opens a hatch and rebuilds round it. (DEV_GUIDE: *Never find a door by
  its sprite*.)
- **A test that jumps a player between decks has to wait for the ground.**
  At a pitch of 32 the neighbouring decks were loaded anyway; at 108 they are
  not, and a two-tick pump after a jump left an arrival hold running.
- **The simulation had no stance at all** -- no `setVariable`, no
  `setSneaking` -- and a stub that is missing throws inside `U.try`, which
  would have looked like a quiet no-op. They store what they are given now, so
  a test reads back what the crawl set.
- **A tube is a room too.** The tube strip beside a deck is inside that
  deck's box, and every count of "what stands on deck k" had to learn to
  leave the tube's squares out.
