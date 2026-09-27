# The Field Station

The working guide to Field Station Muldraugh: a Starfleet survey base under an
ordinary electronics store, reached through a breaker box in its stockroom
that is not a breaker box, three sublevels deep, and staffed. `ADIRONDACK.md`
is how the ship is raised at runtime; this station is raised by the same
machinery, and this file is what is different about it.

Built 2026-09-27. **Nothing here has been seen in game yet.** Section 10 is
what to check first; section 12 is what building it taught.

`DEV_GUIDE.md`'s *Rules that exist because they were broken* and
`MULTIPLAYER.md` apply to every line.

---

## 1. What a player gets

- **An electronics store in Muldraugh** (the strip on the main road, beside
  the Zippee), exactly as the map has it, with one thing added: a grey
  **breaker box** on the bare stretch of its stockroom's west wall.
- **Right-click the box: *Open the breaker box*.** Behind the door is not a
  fuse in sight but a Starfleet lift panel. From then on the box is gone and
  the panel is there, for everybody, for the life of the world.
- **Right-click the panel: *Lift: down to the field station*.** The stockroom
  floor hums and drops away, and you step out of a lift car on Sublevel 1.
- **Three sublevels**, joined by the lift, in the Adirondack's own fittings
  (her bulkheads, deck plate, sliding doors, consoles and furniture), with no
  viewports -- you are underground:

  | Sublevel | What is on it |
  |---|---|
  | 1 | Operations (the wall of screens that watches the county), the security office and its arms lockers, survey records |
  | 2 | The mess and galley, the bunk room and its washroom, the infirmary |
  | 3 | The reactor room (a warp core scaled for a station), stores, the survey lab |

- **Starfleet crew walking the sublevels in uniform**, as they do on the
  Adirondack: out of the lift, to their posts, sitting, talking to each other
  and to you, and back to the lift. Their talk is their own (section 7):
  these are people who have lived underground since June.
- **Its own power**: a replicator, a Doctor's station on every sublevel, and
  a core that holds its own dilithium, billed to the station and never to the
  shuttle or the Adirondack.
- **The way out is the lift**: from any sublevel's lift car, *Up to the
  stockroom*. There is no transporter down here, and no beam to the shuttle.

## 2. The fiction

Binding on anybody writing a line for it, and taken from `LORE.md` 1a-1c and
`CREW.md` 2.

**It is a duck blind.** The Federation has done this before and on the
record: the Mintakan observation post in TNG's *Who Watches the Watchers* was
an anthropological station hidden from the people it watched. Shepard's
department ran this one. The detachment bought a failing electronics shop in
Muldraugh -- cover, and a steady supply of the 1993 hardware a cultural survey
wants to take apart -- and dug the station under it.

**This is where the television came from.** `LORE.md` 1a has Shepard
acquiring the cabin's television and its tape deck as specimens. She did it
here. The crew down here know which set she took.

**Who is down here: part of the eleven.** `CREW.md` 2: eleven of the crew were
on the surface and chose to stay for the fieldwork. Some have been beamed up
since; the Adirondack does not know about the rest, and not knowing is a
wound. **Some of them are here.** When the county died in two days at the end
of June they sealed the station, raised its masking field and went silent,
because whoever did this knows how Starfleet thinks. The Adirondack logged the
field office as dark on 29 June and has not heard from it since.

What that settles:

- **The crew down here are alive and working**, and they are careful. They
  are the survey: they watch the county on their screens, keep records of the
  dead as people, and argue about whether to break silence.
- **They know the Adirondack is up there.** They do not call her. The masking
  field hides the station from her sensors as much as anybody's, and they
  think that is the point.
- **They do not know who you are**, any more than the ship does. In uniform
  you are a surprise; out of it you are an alarming one, who got past the
  breaker box.
- **Every rule in `CREW.md` 2 holds**: no real likenesses, no canon speakers,
  the Changeling never stated, nothing cruel about the dead, lines of 80
  characters at most.

The Adirondack's crew mention the field office now and then -- the dark one,
behind the shop in Muldraugh -- which is how a player hears where it is.

## 3. The store and the secret door

### Which store

`C.FieldStation` in `TREK_Config.lua` names the site, and nothing else in the
code knows a coordinate:

| | |
|---|---|
| Building | Muldraugh's electronics store, 10602-10621 x 9600-9620 (with the Zippee in the same strip) |
| Room | `electronicsstorage`, the stockroom behind the shop floor |
| The box | 10602,9604, on the stockroom's west wall |

It was chosen by reading the map, not by walking it: `tools/fieldstation_site.py`
parses the vanilla `lotheader` (the rooms and their names) and `lotpack` (the
tiles on each square) and prints the stockroom square by square, with the
server's own rule applied to each. 10602,9604 is the only square in it that
passes: the north wall is an interior window, and the rest of the west wall
carries a workbench, a stove and the notices pinned above them.
`tests/test_assets.py` runs the same rule against the installed map on every
run, so a game update that moves that wall fails at the desk.

**The server checks the site before it touches it**, in every world: the
square must be in a room of that name, carry a solid wall on the named edge
(`WallW`/`WallN`, never a window or a doorway), and have nothing standing on it
but that wall, its trim and grime -- and trim means any tile marked
`WallOverlay`, which is how the map paints a wall (section 12). If the map is not the one it was read from
(another map mod, a later game version), the server walks every square of the
same room for one that passes, and if none does it says so with a `WARN` and
places nothing. It never builds a door into a wall it has not checked.

### The box, and what is behind it

Two tiles on the Adirondack's furniture sheet, both hung on a wall:

- **`fuse_box`** -- the disguise, a new flat piece (the last in
  `tools/adirondack_objects.py`): a scuffed grey 1990s breaker cabinet with a
  yellow warning triangle. Its picture is drawn by `tools/gen_fuse_box.py`,
  procedurally, because it is a grey box and an image model has nothing to add
  to one.
- **`turbolift_panel`** -- what is behind it, the same panel the Adirondack's
  lift cars carry.

**Placing and revealing are the server's**, in `TREK_FieldStationServer.lua`:

1. The box is placed the first time anybody loads the stockroom's chunk, once
   ever (`placed`), tagged `fst`. Placed rather than shipped, for the cabin's
   reason: the mod does not edit a vanilla map cell.
2. `stationOpen` (a client asking, from within reach of the box): the server
   checks the player is standing in reach on its own copy, takes the box away
   and hangs the panel in its place, and records `found`. It is published in
   the ship state as `s.station` -- the site square and `found` -- so every
   client offers the right option on the right square.
3. A world where the box was taken (a sledgehammer, another mod) gets it back
   on the next load of that chunk, and a found panel likewise. The lift is
   world furniture and cannot be lost.

### Going down and coming up

Two new moves in `TREK_Server.lua`'s `MOVES`, asked and granted like every
beam (`Core.requestMove`):

| Move | From | Server checks | Charge |
|---|---|---|---|
| `stationDown` | the panel | found; standing within `C.FieldStation.reach` of the panel square | 1 |
| `stationUp` | a station lift car | on a station sublevel, in its lift car | 1 |

Both are one long move of the player's own character, so both take one
transporter charge on a server with the speed anti-cheat, as every beam does
(`MULTIPLAYER.md`, *Transporter charge*). Neither costs power: it is a lift.

- **Down** arrives in Sublevel 1's lift car and holds there until the server
  says the sublevel is built, exactly as a turbolift ride does on the
  Adirondack (`adkBoarded` / `adkReady`).
- **Up** arrives on the stockroom floor in front of the panel. The ground
  there is Kentucky, real map, so the only wait is for the chunk to stream in:
  held on the spot until the square has its floor, then let go.
- **The return point is the stockroom.** The server writes it on its own copy
  of the player before the move (as it does for a beam up), so anything that
  asks where a player in the station *is* on the map -- a distress call's
  distance, a probe -- answers the store (`Ship.worldOrigin`).

## 4. The station

### The sublevels

Drafted as BuildingEd sections by `tools/gen_adirondack_sections.py` (the
three `fs_*` entries, written to `design/buildinged/FieldStation_*.tbx`),
composed into sublevels by `tools/compose_adirondack.py` (the `STATION`
list), each with the Adirondack's spine corridor, lift car, wash basin and
EMH station, exactly as a deck has them.

| Sublevel | Section | Rooms |
|---|---|---|
| 1 | `fs_operations` | Operations, Security Office, Survey Records |
| 2 | `fs_habitat` | Mess, Bunk Room, Washroom, Infirmary |
| 3 | `fs_reactor` | Reactor Room, Stores, Survey Lab |

Once the author saves a section in BuildingEd it is theirs (the generator's
`Generator` property, `ADIRONDACK.md` 8).

### One layout, two places

**The station is more decks of the same layout, not a second system.** Every
sublevel is an entry in `L.decks` with `site = "fst"`; the Adirondack's are
`site = "adk"`. Everything `ADIRONDACK.md` 9 says about a deck is true of a
sublevel: built by the server per sublevel as a player arrives, tagged `adk`,
refitted in place when the layout changes, doors that open as you walk up,
water topped up, machines found by piece name, lamps hung by each client.

What the site changes, and nothing else:

| | Adirondack (`adk`) | Field station (`fst`) |
|---|---|---|
| Where in the void | decks 1-5, 108 apart | sublevels 1-3, from slot 8 (864 squares east of Deck 1), 108 apart |
| Under the floor | stars | black: nothing at all (`gen_void_map.py`) |
| Jefferies tubes | between her decks | none |
| The lift lists | her decks | the sublevels, and *Up to the stockroom* |
| The way out | *Beam back to the shuttle* | the lift up |
| Power | her store, `s.adk` | its own, `s.fst` (`A.StationStartCrystals`) |
| Crew talk | `where: any` and her places | `where: station` and the station's places |
| The menu's title | U.S.S. Adirondack | Field Station |

`A.siteOf(k)` answers the site of a deck, `A.siteAt(x, y, z)` of a square and
`A.siteOfPlayer(p)` of a player. `A.onShip(player)` keeps its meaning --
standing on any runtime deck, which is what the machines' menus, the Doctor
and the deck builder ask -- and `A.onAdirondack(player)` / `A.onStation(player)`
are the two halves for the few things that differ.

**Sublevels stand far east of the ship**, not after her: the star field under
the Adirondack reaches 110 squares past her last deck (`gen_void_map.py`,
`VIEW`), and the station's black should not begin where anybody can see stars.
Slot 8 leaves 280 squares of nothing between the last star and Sublevel 1.

**Deck numbers are the station's own.** The layout generator used to order
decks by the number at the end of the name (`Deck 4` -> 4). A second "Sublevel
1" would sort against "Deck 1", so the order is by site first, then number,
and the Adirondack's five keep the indices every save has already built.

### What the lockers hold

`A.Stock`, by piece, as on the ship. The station adds no new container pieces
and changes nothing the Adirondack's lockers hold; what is in the station's is
decided by what stands there. Worth knowing: every stocked container is
stocked once, when it is made (`DEV_GUIDE.md`, *Never restock*), so the
station's lockers fill when the sublevel is first built in a world -- in an
existing save as much as a new one, because none of it existed before.

## 5. Who owns what

| | |
|---|---|
| The site square, placed, found | **Server**, `TREK_FieldStation` mod data; `found` and the square published in `s.station` |
| The box and the panel | **Server**, world objects, tagged `fst`, placed with `transmitAddObjectToSquare` and taken with `transmitRemoveItemFromSquare` |
| Opening the box | **Server**, on `stationOpen`, measured on its own copy of the player |
| Going down and up | **The player's own client** moves its character, after the server grants `stationDown` / `stationUp` |
| The sublevels | **Server**, the Adirondack's deck builder, per sublevel |
| The station's power | **Server**, `s.fst`, spent through the one ledger (`TREK.Energy.energize`) under `P.using("fst")` |
| The crew | **Server** scripts; **the owning client** walks (`CREW.md` 6) |

`TREK_Net` serves every command from a player standing in the station under
the station's store, as it serves a player on the Adirondack under hers. The
shuttle's lamps, dark notes and warnings are the shuttle's alone
(`TREK_Energy`), for any store that is not hers.

## 6. Power

`TREK_Power` had two stores, the shuttle's (`s` itself) and the Adirondack's
(`s.adk`). It has three now. Every function takes the pool as before;
`P.poolOf(player)` answers `fst` in the station. The station starts with
`A.StationStartCrystals` (12) in its core, loaded and taken like any core
through its warp-core piece on Sublevel 3, and its galley range has its own
power bus, billed to it.

Twelve is deliberate: enough to run the replicator and the Doctor for a long
time, not enough to make the station a better base than the shuttle.

## 7. The crew and their talk

The Adirondack's crew system, unchanged, on three more decks
(`K.Population`, `K.Jobs` gain three entries). Their talk is
`design/crew/station.txt`, compiled with the rest by `tools/gen_crew_talk.py`.

### Places

| Tag | Room |
|---|---|
| `ops` | Operations, the Security Office |
| `records` | Survey Records, the Survey Lab |
| `mess` | the Mess |
| `bunks` | the Bunk Room, the Washroom |
| `infirmary` | the Infirmary |
| `reactor` | the Reactor Room, Stores |
| `shaft` | a station lift car, a sublevel's corridor |
| `station` | anywhere in the station |

**`any` means anywhere on the Adirondack, and `station` anywhere in the
station.** The ship's `any` scenes talk about orbit, the lounge viewer and the
galley upstairs; played in a bunker they would be wrong. `TREK_CrewServer`
matches `any` on an `adk` deck and `station` on an `fst` one, and a room's own
tag on either. The station therefore has its own `hello`, `outfit`, `idle`,
`arrive` and `leave` barks.

### Who they are

The same roster -- species, ranks, divisions -- weighted for a survey
detachment: sciences first, then operations, a little command.

## 8. Files

| File | What |
|---|---|
| `FIELD_STATION.md` | this guide |
| `TrekShuttle/42/media/lua/shared/TREK/TREK_FieldStation.lua` | the site: where the box is, what counts as reach, which sprites |
| `TrekShuttle/42/media/lua/server/TREK/TREK_FieldStationServer.lua` | placing the box, opening it, the site check |
| `TrekShuttle/42/media/lua/client/TREK/TREK_FieldStationClient.lua` | the box's and the panel's menus; down and up |
| `TREK_Adirondack.lua` | `site`, `siteOf`, `onAdirondack`, `onStation`, the station's crystals |
| `TREK_AdirondackClient.lua` | the lift per site, the menu's title, the stockroom option |
| `TREK_Server.lua` | the two moves |
| `TREK_Power.lua`, `TREK_Net.lua`, `TREK_Energy.lua` | the third store |
| `TREK_Crew.lua`, `TREK_CrewServer.lua` | three more decks; `station` for `any` |
| `TREK_Config.lua` | `C.FieldStation` |
| `tools/gen_adirondack_sections.py` | the three `fs_*` sections |
| `tools/compose_adirondack.py` | `STATION`, the sublevels |
| `tools/gen_adirondack_lua.py` | `site`, the station's slots, its place tags; tubes only between the ship's decks |
| `tools/gen_void_map.py` | the station's cells, black |
| `tools/adirondack_objects.py`, `tools/gen_fuse_box.py` | the breaker box |
| `tools/fieldstation_site.py` | reads the vanilla map and prints the stockroom |
| `design/crew/station.txt` | what the station's crew say |

## 9. Testing

```sh
python tools/luacheck.py TrekShuttle/42/media/lua
TREK_ONLY=fieldstation,fieldstation_multiplayer,adirondack,jefferies python tests/test_multiplayer.py
python tests/test_assets.py        # includes the site, read off the installed map
python tests/test_crew.py
python tools/fieldstation_site.py  # the stockroom, square by square
```

The simulated stockroom (`FS_STOCKROOM` in the test) is the real one in
miniature: the room's name (`SIM.room`), the west wall with its trim on every
square, a workbench on the next square down and the interior window along the
north. `tests/pz_sim.lua` learned two things for it: a tile's own flags
(`SIM.tileProps`, read through `getProperties():has`) and a square's
`getRoomDef()`. Before, every flag answered false -- a stub that would have
passed a box hung on a window.

**`fieldstation()`**, single player and with two clients:

- the layout: three sublevels with `site = "fst"`, far enough east, no tube
  touching one, a lift car on each lined up with the ship's;
- the box: placed once on the checked square, refused on a square with a
  window, and found again in the room when the named square will not do;
- opening: refused out of reach, granted in reach, the box gone and one panel
  on the wall, `found` published to the second client;
- down and up: refused before the box is open and from the wrong place,
  granted, Sublevel 1 built and the arrival released, the return point the
  stockroom on the server's own copy, up again to the stockroom floor;
- the lift: only sublevels offered in the station, only decks on the ship;
- power: a replicator on Sublevel 2 bills `s.fst` and nothing else;
- crew: a sublevel staffed; `station` talk matched there and `any` never.

**`fieldstation_multiplayer()`**: one player opens the box and the other's
client shows the panel; a ride down asked for from the street is refused; the
server holds the stockroom as the return point of a player below, on its own
copy, and bills them to the station's store.

**Fifteen mutations, one at a time, each asserted to have applied, all
caught** -- two only after their test was tightened: the ride down before the
box is open was also out of reach, and the ride up from the stockroom was also
not from a lift car, so in each case the other guard refused first. The test
now asks at the box, and from the Adirondack's own lift car.

## 10. Not yet seen in game

In a world where the stockroom's chunk has not been loaded since this was
installed (any new world; most existing ones -- only a player who has stood in
that store since will have missed the placement, and the next load fixes it):

1. **The box.** Muldraugh, the electronics store beside the Zippee, the
   stockroom, the west wall: a grey breaker cabinet. Does it read as 1993?
2. **Opening it.** The note, and the panel where the box was.
3. **Down.** The note, the lift car, Sublevel 1 building round you, the log
   saying `Field Station Sublevel 1 built`.
4. **The sublevels.** No stars under the floor, black; the doors; the lamps;
   the lift between them.
5. **The crew.** Walking, sitting, and the station's own talk.
6. **Up.** Back on the stockroom floor, in front of the panel, not in a wall.
7. **The replicator and the Doctor** on the station's own power.
8. **Two players**: one opens the box, the other sees the panel.

## 11. Open decisions for the author

- **The store.** Muldraugh's electronics store is the pick because the
  television came from one; `C.FieldStation` takes any other building whose
  room name and wall square pass the check.
- **A hint in the world** beyond the Adirondack crew's talk: a line on the
  comms channel, or the station as a probe's result, are both natural and
  neither is built.
- **Breaking silence**: whether the station ever calls the Adirondack, and
  what happens when it does, is a story decision and is left open.

## 12. What building it taught

- **A wall on the map is more than its wall tile.** Every wall of that
  stockroom carries a second tile, `location_trailer_02_48`: no picture of
  its own worth the name, flagged `WallOverlay`, `attachedW`. The first rule
  called anything wall-attached that was not the wall "occupied", passed every
  test -- the simulated stockroom had no trim -- and would have found nowhere
  in the room to hang the box, in every world, with a WARN nobody reads. It
  was caught by running `tools/fieldstation_site.py` against the real map
  before the game, which is why that tool exists and why `test_assets.py`
  runs it. The simulated wall carries the trim now.
- **Two guards that refuse the same case hide each other from a mutation**
  (DEV_GUIDE, *A correction that cannot succeed must be allowed to stop*):
  see the two tightened tests in section 9.
- **A counter across "every deck" is a counter across both places.** Adding
  three sublevels broke four of the Adirondack's own checks -- her lockers'
  totals and the tube count -- because they walked `L.decks`. They walk her
  site now (`adk_items(..., site)`, `A.decksOf("adk")`).
- **Asking for a patient "aboard" with no asker meant the cabin.** The
  Doctor's server-side patient lookup (`EMH.patientNamed`) took no asker and
  so always searched the shuttle's cabin: on the Adirondack nobody but
  yourself could ever be treated. It searches the asker's own place now --
  cabin, ship or station -- which fixed the ship as a side effect.
