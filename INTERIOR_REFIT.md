# The interior refit: 54 squares down to 24, and then Starfleet issue

**Built at revision 17, and changed since** by the EMH's station (revision 23),
the tape shelf (27) and the galley's power bus (`ENERGY.md` 9.1). **Played:**
the television, which plays the shelf's tapes. The rest of the list in section
7 has not been walked, and the migration from a 6x9 save has not been seen.

> **Revision 35 refitted the cabin again, in Starfleet issue: section 9.**
> Sections 2 and 3 describe the vanilla-furnished cabin of revisions 17-34 and
> are kept as the record of why it was shaped the way it was; the deck plan,
> the fittings and the migration that are live now are in section 9, and
> `python tests/test_layout.py` prints the plan as it is.

The cabin is four squares across by six fore-and-aft, the lockers hold nothing
but the mod's own items, and five of the nine containers start empty on
purpose. This file is the working guide: what it is, why each piece is the way
it is, the five traps the pass found, and what to look at the first time it is
carried into a game.

`DESIGN.md` says how to change the ship. `DEV_GUIDE.md`'s *Rules that exist
because they were broken* applies to every line of this.

---

## 1. Why

The hull is a 3×5 world model: fifteen squares of ground. The cabin behind the
transporter was fifty-four. Walking into a shuttlecraft and finding eight
lockers, two fridges, a two-tile oven, a berth and a cargo bay does not read as
a shuttle — it reads as a warehouse that a shuttle is parked next to.

Four by six is **twenty-four squares**: one wider and one longer than the hull
itself. Close enough that the inside and the outside tell the same story, and
still enough room to give every system a place a player can find without a map.

---

## 2. The deck plan

`ox` runs 0..3 port to starboard, `oy` runs 0..5 bow to stern.
`C.CabinW = 3`, `C.CabinL = 5`.

```
    0123
  0 TVLA        T monitor wall (wall object, deck underneath)   A armoury
  1 F*.p        V television on its console   L tape shelf (wall)   p rations
  2 oh.M        F fridge   * lamp   h crew seat, facing the screen   o oven
  3 wD.H        M sick bay   w sink counter   D the warp core
  4 m*.B        H the EMH's station overhead, and where he stands (kept clear)
  5 R.@B        m microwave counter   B biobed   @ transporter pad
                R the replicator
```

`python tests/test_layout.py` prints this with the legend and the container
list; the bow bulkhead also carries LCARS monitors at 0,0, 1,0 and 3,0, which
the plan cannot draw because they are wall objects sharing those squares.

Eleven squares carry a blocking fitting and twelve are open deck — including
0,0 and 2,0, which look occupied on the plan and are not: the monitor wall is
a wall object and the deck under it is walkable.

**The seat is a theatre chair and that is load-bearing.**
`location_entertainment_theatre_01_3` carries `collideN` and `HoppableN` only:
it blocks its north edge and nothing else. That is what lets it stand in the
middle of the deck at 1,2 without cutting the cabin in half, and it is why you
sit down from the south. Swap it for one of the two-tile bench seats — plain
`solidtrans` — and it becomes a wall.

Everything is reachable from an open square:

| Fitting | Opened from |
|---|---|
| television | 0,0, 2,0 or 1,1 |
| armoury | 2,0 |
| rations, sick bay | 2,1 and 2,2 |
| fridge, oven, sink, microwave, the replicator | the port passage, 1,1 .. 1,5 |
| the warp core | 1,3 itself; worked from 2,3, which the layout keeps clear |
| biobed, the EMH's station | 2,4, the pad at 2,5, and 3,3 under the station |

---

## 3. What is in it

### The bow: the viewscreen wall, a working television, two seats

| Square | Sprite | Tag |
|---|---|---|
| 0,0, 1,0, 3,0 | `security_01_4` | `console` — wall-mounted, blocks nothing |
| 2,0 | `furniture_shelving_01_28` | `tapes` — the tape shelf, a wall shelf; 2,0 stays deck so the armoury can be opened (`LORE.md` 3) |
| 1,0 | `furniture_tables_low_01_3` | `tvConsole` |
| 1,0 | `appliances_television_01_1` | `television`, `device = "Base.TvWideScreen"` |
| 1,2 | `location_entertainment_theatre_01_3` | `chair`, facing N |

The television sat in the port bow **corner** at 0,0 for one revision, tucked
in behind the fridge where you had to be standing on a chair to use it. It is
in the middle of the bow wall now, and the seating went from two chairs beside
it — level with the screen, looking at the bulkhead — to **one chair at 1,2,
two squares back and dead in front of it**, looking at the thing it is for.

**There is no VCR object in build 42 and there does not need to be.**
`appliances_television_01_0..3` is `Base.TvWideScreen`, and its item script
(`scripts/generated/items/radio.txt:436`) carries `AcceptMediaType = 1` — the
tape type. `RWMMedia.lua:235` pulls `Base.VHS_Home` and `Base.VHS_Retail` out
of your inventory and into that device. A television in build 42 *is* a
television and a video player in one object.

**The shelf at 2,0 holds the ship's tapes**: Lt. Shepard's collection, and
the tapes the Adirondack channel issues later (`LORE.md`, `COMMS.md`). They
are the one thing aboard that is not Starfleet issue, and the fiction says
why: the cabin is hers.

**And it has power, which took a second pass.** See §5 — the cabin is not on
the town grid, has no generator, and cannot be given electricity by telling
its squares they have some. `TREK_Power.lua` gives every powered fitting its
own cell and keeps it full, in every process.

### Port: the galley — all of it the player's storage

| Square | Sprite | Tag | Holds |
|---|---|---|---|
| 0,1 | `appliances_refrigeration_01_1` (cap 40) | `fridge` | nothing |
| 0,2 | `appliances_cooking_01_4` (cap 15) | `oven` | nothing |
| 0,3 | `fixtures_counters_01_35` | `counter` | nothing |
| 0,3 | `fixtures_sinks_01_1` | `sink` | water |
| 0,4 | `fixtures_counters_01_35` | `counter` | nothing |
| 0,4 | `appliances_cooking_01_24` (cap 5) | `microwave` | nothing |

Four squares, five appliances: the sink and the microwave ride on counters
rather than taking squares of their own. **The oven and the microwave are real
`IsoStove`s and the fridge really cools**, powered by a generator nobody sees
on the hull ring beside the oven (`TrekPowerBus`, `ENERGY.md` 9.1), billed
from the reserve and switched off when the ship is dark. The fifth galley square, 0,5, is the
replicator's and carries no fitting -- the machine is the whole thing there.

**The oven is one tile now.** The old galley used `appliances_cooking_01_40`
and `_41`, the two halves of one range — a quarter of the new cabin on its own.
`appliances_cooking_01_4` is the single-tile grey Oven from the same set,
`IsoType = IsoStove`, `container = stove`, capacity 15. Same cooking, one
square, and grey suits a metal hull better than the green one.

**0,5 is the replicator's, and it carries no fitting at all.** It was a bare
steel counter until the machine arrived on 2026-09-20 -- first with a model
hanging over the counter and replicated items going into the counter's own
container, which was half a machine leaning on a piece of furniture. The
counter is gone from the `.tbx` and the layout: `C.ReplicatorSpot` names the
square, `TREK_Build` stands a full-height world model on it, and what the
machine makes goes into the player's hands. `B.refitCabin` takes the counter
out of a save that still has one, and spills what was in it onto the pad.
`REPLICATOR.md`.

**1,3 is the warp core's, and it carries no fitting at all.** The second
square in the cabin to be owned by a model rather than a tile, for the same
reasons as the first.

It was a vanilla Tool Cabinet (`location_business_machinery_01_33`,
`container = toolcabinet`, capacity 20) for one revision. That worked
perfectly and looked like a tool cabinet — which, for the ship's power plant,
is the same failure the helm prop had in reverse. It is the mod's own model
now (`tools/gen_warpcore.py`): a banded plasma column with a lit crystal in
its collar, slim enough to stand in a passage the crew walk down.

**It has no container, and it does not want one.** A container comes from a
tile sprite's properties, so a custom model cannot have one, and standing the
model over the cabinet to borrow its container is the arrangement the
replicator was rebuilt to get rid of. What it holds is one number in the ship
state, loaded and unloaded from its right-click menu. `REPLICATOR.md` is the
system; this is the furniture.

The cabinet did leave one lesson behind: `tests/pz_sim.lua` decides whether a
sprite has a container from a list of substrings in its name, and
`..._machinery_...` was not one of them, so it was placed, never stocked, and
eight checks failed on a power system that was working perfectly. The list
still needs a new entry for any *tile* fitting that holds something.

The sink is the only plumbed fixture left. `C.WaterTags` keys on the tag, so
nothing in the water code changed.

### Starboard forward: three Starfleet lockers

All three are `furniture_storage_02_11` — Locker, facing W, capacity 40.

| Square | Tag | `special` | `loot` | `cap` | Ends up holding |
|---|---|---|---|---|---|
| 3,0 | `armoury` | `phasers`, `uniforms`, `padds`, `packs`, `lamps` | `weapons` | 8 | 4 phasers, 2 each of the 4 blades, 1 of each of the 6 uniforms, 2 PADDs, 1 field pack, 2 shoulder lamps |
| 3,1 | `provisions` | — | `food` | 27 | 27 from the 18-item food list: the dishes and the drinks |
| 3,2 | `medical` | `medkit` | `medical` | 8 | 3 each of the 4 instruments |

`C.PhaserRack` follows the armoury to 3,0; `tests/test_layout.py` holds the two
in step.

**The armoury took the wardrobe too** (2026-09-23). `special` is a list now,
because a container can owe more than one guarantee and four phasers and one
uniform of each division are two different counts. The locker ends up at 25.8
of its 40 units — 2.4 of phasers, 15.0 of blades, 8.4 of uniforms — so nothing
is dropped for want of room, and `U.stockEach` reads it back either way. With
the PADDs, the field pack and the two shoulder lamps (2026-09-29) it is 28.0.

It is the armoury and not a wardrobe of its own because the cabin has three
Starfleet lockers and none of them is a slop chest: 3,0 is where the crew's
issue lives, which is sidearms, blades and what they wear. A fourth locker is
a change to the `.tbx` in BuildingEd, not to the Lua. `UNIFORMS.md` is the
working guide.

### Starboard aft: the sick bay and the EMH's station

| Square | What | Tag |
|---|---|---|
| 3,3 | the EMH's projector station, the mod's own model, mounted high on the east bulkhead | a world item, `C.EmhStationItem` |
| 3,3 | the Doctor, projected directly below it when he is up | a world item, `C.EmhItem` |
| 3,4 / 3,5 | `location_community_medical_01_17` / `_16` | `biobed` |

The station and the Doctor share 3,3, and the layout keeps that square clear.
Until revision 23 the station was a vanilla wall panel (`industry_01_15`, whose
`CustomName` is "Air Conditioner", and which looked like one) and the Doctor
stood at 2,4 in the middle of the room. `B.serviceEMH` removes both from older
cabins. `EMH.md` is the working guide.

**Not a light switch.** `lighting_indoor_01_0..7` is the obvious "wall button"
and every one of them carries the `lightswitch` tile property, which is what
the cell loader reads when it decides to build an `IsoLightSwitch` instead of
an `IsoObject`. A button that becomes a real light switch on the next world
load is a bug that only shows up in somebody else's save.

**The bunk is gone and the biobed replaces it.** Both halves carry
`BedType = goodBed`, so it is a proper bed. A shuttle with a sick bay *and* a
berth in twenty-four squares is a shuttle with nowhere to stand. `C.Pieces.bunkS`
was deleted with it.

### The helm, the pad, the lights

- **There is no helm console object.** There used to be: a 70-weight static
  model (`TrekHelmConsole`) standing on the deck. It did nothing. The helm
  panel opens from the aboard menu — right-click anywhere aboard →
  *Shuttlecraft* → *Helm* — and never from that object, so in a fifty-four
  square cabin it read as furniture and in twenty-four it was a big box in the
  middle of the room. `furnishHelmItem` is gone and `B.refitCabin` removes the
  ones already lying in existing saves.
- **Transporter pad — 2,5.** Aft, beside the foot of the biobed. It was
  amidships at 2,2; aft means materialising puts the length of the ship in
  front of you rather than half of it behind — you arrive at the sick bay,
  walk forward past the lockers and the galley, and the viewscreen is what you
  are looking at. It has exactly two ways off it (1,5 and 2,4), which is the
  minimum `tests/test_layout.py` allows, so anything added on either of those
  squares will fail the check rather than box the pad in.
- **Lamps — `{1,1}` and `{1,4}`.** Two, not three; `lighting_indoor_01_32` is
  non-solid so they only need squares nothing else wants.

---

## 4. Starfleet issue only

> *"since we have fewer lockers we should have all custom mod items only and
> not a bunch of vanilla items — players will fill storage with vanilla items
> as they play"*

That is the second half of the refit and it is why `C.Loot` is four lines long
now instead of nine lists.

- **Five of the nine containers hold nothing.** The fridge, the oven, both
  counters and the microwave are the player's shelves. The ninth is the tape
  shelf. (The replicator replaced the counter it used to stand on, a dilithium
  cabinet came and went, and the warp core replaced that.)
- **The three lockers hold the mod's own items and nothing else.** A locker of
  pistols and bandages was what a 40-unit container needed when there were
  eight of them; with three it is just the vanilla game, in a cupboard, on a
  spaceship.

```
C.Loot.medical   4   hypospray, dermal regenerator, medical tricorder, tricorder
C.Loot.food     18   the eleven galley dishes and seven drinks (ITEMS.md)
C.Loot.weapons   4   bat'leth, mek'leth, lirpa, ushaan-tor   (phasers via `special`)
C.UniformIssue   6   duty and dress uniforms, command/operations/sciences
                     (all six via `special`, one each, not rolled)
```

`C.Loot.fresh`, `cookware`, `tools`, `linen` and `survival` are deleted
(`drinks` came back later, for the Adirondack's bar). Nothing pointed at them any more, and `tests/test_stock.py` reads its
list names out of the layout, so a list nothing uses is a list nothing checks.

**Quantity is a decision, not an outcome.** Each locker carries `fill = 1.0`
and an explicit `cap`, which puts the weight target out of the way and lets the
item count decide. Every cap is a multiple of its list length, so each item goes
in the same number of times whatever the rolling cursor is doing.

> **TRAP — three containers cannot spread a list the way nineteen did.**
> `U.stock` walks each list from a rolling cursor, which is exactly what made
> nineteen lockers show thirty-one different medical items. Three lockers take
> three bites, and a locker that happens to miss the ushaan-tor looks exactly
> like one that does not. The caps solve it arithmetically; `special` +
> `U.stockEach` braces it by reading the container back and reporting what did
> not land.

`tests/test_multiplayer.py` now asserts the thing that actually matters rather
than counting containers: **every id in all three lists is aboard a freshly
built cabin, and nothing that is not `TrekShuttle.*` is.** Counting containers
could not see a locker quietly losing its loot list, because the count of
containers wanting stock falls with it and the two still agree. Both mutations
were checked.

---

## 5. The five traps this pass found

### The viewscreen was never a television

`place()` builds every fitting with `IsoObject.new(sq, sprite, tag)`, which
produces a plain `IsoObject` wearing a television's picture: no device data, no
channel, no tape slot, nothing to right-click. That is what the cabin's
viewscreen has been for three versions, and nobody noticed because nobody ever
tried to turn it on. It is the same *present, drawn, and inert* shape as the
unopenable locker and the tap with no water store.

The fix is a `device` field on the layout entry and a `placeDevice()` that uses
vanilla's own constructor (`ISMoveableSpriteProps.lua:2136`):

```lua
local obj = IsoTelevision.new(getCell(), sq, getSprite(sprite))
obj:setDeviceData(obj:cloneDeviceDataFromItem("Base.TvWideScreen"))
```

`IsoWaveSignal.cloneDeviceDataFromItem` is the better of the two routes and was
found by disassembling it: it caches per id and hands back a *clone*, and it
reaches `InventoryItemFactory.CreateItem` **in Java**, which works even though
the Lua global of that name is null. Neither route has a vanilla *Lua* call
site, so both are tried and `getDeviceData()` is read back and logged —
`[TREK] device: Base.TvWideScreen is live`. A television with nil device data
looks identical to a working one until somebody walks up to it.

### The cabin had no electricity, and the call that was supposed to give it some did nothing

The television went in, was built as a real `IsoTelevision` with real device
data — and would not switch on. The cause was one layer down and it had been
there since the cabin was first written.

`B.powerCabin()` walked every square of the cabin calling
`sq:setHaveElectricity(true)`, at build time and again every game minute. It
was a no-op:

- **`setHaveElectricity(boolean)` sets no field.** Its bytecode walks the
  square's objects and touches `IsoLightSwitch`es. The cabin has none.
- **`haveElectricity()` is not a flag.** It returns
  `chunk.isGeneratorPoweringSquare(x, y, z)` — a real running `IsoGenerator`.
- **`hasGridPower()`** is the town mains, which shut off a few weeks in.

So the two ways to be mains-powered out here are a generator standing in the
cabin — a large object to look at, a fuel supply to keep filled, and exactly
the kind of thing that had just been taken *out* of a twenty-four square room
— or the town grid, which is temporary by design. Neither is a spaceship.

The answer is one branch further in. `DeviceData.canBePoweredHere()` opens
with `if (isBatteryPowered) return true`, **before it looks at the square at
all**, and that is what both `setIsTurnedOn` and the per-minute `update()`
consult. So the shuttle's power plant is that there isn't one: every powered
fitting has its own cell, and `TREK_Power.lua` keeps it full.

Three things the disassembly settled:

- **A battery-powered device switches itself off at zero.** `update()` drains
  the item script's `UseDelta` per game minute — 0.007 for a television, so a
  full cell is about two and a half game hours — and the stay-on test is
  `isBatteryPowered && power > 0` *before* it falls through to
  `canBePoweredHere()`. "Battery powered" is not "powered for ever".
- **The top-up runs in every process**, which is why `TREK_Power.lua` is
  shared and not server-only. `DeviceData.update` drains the value wherever it
  runs and a client transmits the drop itself, so a server-only top-up would
  leave every client switching the television off after a couple of game
  hours. It is a value the engine recomputes per process, like the deckhead
  lights and the shields — not ship state, and nothing is published.
- **`hasBattery` stays false.** The engine never reads it; `RWMPower.lua`
  does, and offers *Remove Battery* when it is true, which would hand the
  player a free `Base.Battery` every time they opened the panel.

`B.powerCabin` is deleted, and so is its per-minute call. `TREK_Power()` from
the console reports each fitting's cell and whether it has device data at all
— the line that tells "the television is off" from "the television is
scenery".

**The water was already right.** `B.refillWater` has run every game minute
since 1.3 and each fixture carries its own `FluidContainer`, so the sink does
not care about the mains shutoff. It has just never been watched in a world
with the mains off, which is still on the list below.

### The old cabin does not go away on its own

Shrinking the cabin is a migration, not a rebuild. `clearSurroundings` sweeps
the margin, but `U.clearSquare` **deliberately preserves anything the mod
tagged** — so every locker, fridge and bunk of the 6×9 cabin would have been
left standing, openable, in the black void outside the hull, for ever.
`forceRebuild` would not have saved it either: it swept `C.CabinW + 2`, which
after the shrink stops short of the old stern row.

`B.refitCabin()` sweeps the old extent (`C.LegacyCabin`, 5 × 8, written down
for exactly this) and removes tagged objects outside the new shape, as the
first phase of `buildCabin`. It also removes the helm console prop, anywhere
in the cabin — that is a *world item*, and `U.clearSquare` leaves world items
alone by design, because that is where a player's dropped things live. Two
things about it are the design rather than tidiness:

- **The chunk is the gate, not the square.** A nil square in a *loaded* chunk
  really is nothing there — which is every square of that extent in a world
  made after the refit. If that counted as "ask again later" the sweep would
  never finish and would walk fifty-four squares on every build for the rest of
  the save. `U.chunkLoaded` decides; `s.refitRev` is only stamped when every
  square was reached.
- **The contents are spilled, not destroyed.** Eleven containers are being
  deleted and what is in them is the player's — the whole *ship is lived in*
  rule exists to protect this. `spillToPad` moves the **live `InventoryItem`**
  onto the transporter pad, not its id: recreating from the full type would
  reset a hypospray's doses and a magazine's rounds, which is the quiet half of
  losing it. `AddWorldInventoryItem(InventoryItem, f, f, f)` is the overload
  vanilla's own scenarios use.

`tests/test_multiplayer.py`'s `refit()` section covers both, and both were
mutation-checked: marking itself done with a square unreached, and dropping the
chunk gate, are each caught.

### A WARN for every container that was empty on purpose

`prepareContainer` logged `WARN container %s received no stock` for anything it
could not stock, and `tests/test_multiplayer.py` fails on any `WARN` the mod
logs. With five containers empty by design that is five warnings a build and a
red test. `wantsStock(entry)` is the distinction: an entry with no `loot` and
no `special` is stamped `TREKStockRev` and left alone — stamped rather than
skipped, so the repair path never mistakes empty-by-design for one of the
containers the old broken builds left unstocked, and fills it years later.

### `tests/test_layout.py` was stricter than the code

Two guards in it were wrong about the goal rather than the engine, which is the
shape `DEV_GUIDE.md` warns about under *A guard is only as good as the goal it
was written from*:

- **The pad's 3×3 clearance ring.** `C.Landing.clearance` is 0, so the
  placement helpers refuse the pad square and nothing else: the ring was never
  enforced at runtime. In a cabin four squares wide a nine-square exclusion
  zone is over a third of the ship for one fixture. What has to be true is that
  you can materialise and walk off, so the check is now **two ways off the
  pad** — one is a dead end, and a dead end is how a build that dropped a
  locker in the wrong place would still read as fine.
- **"Every fitting blocks its square."** Half this cabin's fittings are wall
  objects — the bow monitor bank, the EMH panel — and carry neither `solid` nor
  `solidtrans`. `blocks(sprite)` reads it out of the tile catalogue now instead
  of assuming.

---

## 6. Everything that changed

| Change | Where |
|---|---|
| `C.CabinW` 5 → 3, `C.CabinL` 8 → 5 | `TREK_Config.lua` |
| `C.LegacyCabin = { w = 5, l = 8 }` added | `TREK_Config.lua` |
| `C.Landing` {2,6} → {2,5} | `TREK_Config.lua` |
| `C.LampSpots` → `{ {1,1}, {1,4} }` | `TREK_Config.lua` |
| `C.PhaserRack` {5,6} → {3,0} | `TREK_Config.lua` |
| `C.BuildRev` 15 → 17 | `TREK_Config.lua` |
| `C.Loot` cut to three mod-only lists; six lists deleted | `TREK_Config.lua` |
| `C.Pieces.bunkS` deleted; `C.HelmItem` → `C.LegacyHelmItem` | `TREK_Config.lua` |
| the interior, redrawn 4×6 with `device`, `fill` and `cap` fields | `TREK_InteriorLayout.lua` |
| `placeDevice` / `attachDevice`: a real `IsoTelevision` | `TREK_Build.lua` |
| `wantsStock`: containers that are empty on purpose | `TREK_Build.lua` |
| `B.powerCabin` deleted -- it never did anything | `TREK_Build.lua`, `TREK_Server.lua` |
| the ship's own electricity, and `TREK_Power()` | **`TREK_Power.lua`** (new), `C.DevicePower` |
| a real `DeviceData` with the engine's drain and turn-on rules | `tests/pz_sim.lua` |
| `spillToPad`, `removeWorldItem`, `B.refitCabin`, and a build phase for it | `TREK_Build.lua` |
| `forceRebuild` sweeps the old extent too | `TREK_Build.lua` |
| `furnishHelmItem` deleted; the helm prop removed from old saves | `TREK_Build.lua` |
| the interior redrawn 4×6, plus an EMH-panel furniture entry | `design/buildinged/TrekShuttle_Interior.tbx` |
| `IsoTelevision`, `getSprite`, device data, `ItemContainer.Remove`, the `AddWorldInventoryItem(item, …)` overload | `tests/pz_sim.lua` |
| the pad guard, the `blocks()` catalogue read, new glyphs | `tests/test_layout.py` |
| stores-based stock assertions, the `refit()` section | `tests/test_multiplayer.py` |

The old 6×9 file is kept at `design/buildinged/TrekShuttle_Interior.tbx.6x9.bak`.

The hull, the footprint, the void map and the interior cell are untouched.
`C.Footprint` stays 3×5 — the exterior was never the problem.

---

## 7. What to check in game

All seven static checks pass. None of this has been seen in a game.

**In a fresh world**, in this order:

1. **The shape.** Beam up. It should read as the inside of a shuttle. Walk from
   the pad to every fitting: the bow row via a seat square, the galley down the
   port passage, the sick bay aft.
2. **The three lockers.** 4 phasers, 2 of each blade, the six uniforms and
   two PADDs, a field pack and two shoulder lamps at 3,0; 27 dishes and drinks at 3,1; 3 of each instrument at 3,2. `TREK_Stock()` names every
   container and how full it is.
3. **The five empty ones** are openable and empty — not unopenable, which is
   what a missing `container = true` looks like.
4. ~~**The television.**~~ Played: it switches on and plays the shelf's tapes.
5. **The sink** with *Water Shutoff* set to instant. `TREK_Water()`.
6. **The biobed** as a bed: sleep in it.
7. **The fridge, oven and microwave** cool and heat, off the power bus.
8. **No big box on the deck.** The helm console prop is gone; the Helm panel
   is still on the right-click *Shuttlecraft* menu and must still open.
9. **The walls hold.** Walk into each of the four bulkheads and hold the
   context key: no *Climb over* prompt anywhere, on any wall. Build 42 lets a
   player climb a wall as well as a fence, and it refuses only over a square
   with a roof or an `IsoBuilding` behind it -- which the cabin, raised in a
   cell with no map under it, has neither of. Climbing out landed you on the
   ring of deck the walls stand on, and one square past that is the void.
   `TREK_Core.holdVault` takes `ignoreAutoVault` away while you are aboard and
   gives it back when you leave, so **check the other half too**: beam down,
   find a fence, and climb it. `DEV_GUIDE.md`'s *A wall keeps a player in only
   where the engine thinks there is a building*.

**In a save made before today** — keep one, this is the only way to test it:

10. **The migration.** Beam up and look outside the hull. No lockers left
    standing in the void, and the contents of the eleven deleted containers in
    a pile on the transporter pad. `grep "refit:" console.txt` reports what it
    removed and spilled, and says so again on the next build if part of the
    old cabin had not streamed in yet.

**Then on the dedicated server**, because a second client sees none of this for
free: the cabin and its stock reaching a client, and whether a runtime
`IsoTelevision`'s device data replicates.

## 8. Still open

- **A custom biobed.** A custom *tile* needs a TileZed-packed texture pack and
  is out of this pipeline; a custom *world model* is the helm's proven route
  but carries no `BedType`, so the vanilla sprite has to stay underneath and
  the model goes over it as a scanner canopy. An art pass of its own, after
  this is in a game.
- **Deleting the helm console's assets.** The `item TrekHelmConsole` and
  `model TrekHelmConsoleModel` blocks, `TREK_Helm.x`, `TREK_Helm.png` and
  `tools/gen_helm.py` are all still in the tree, deliberately: saves made
  before this have a world item of that type on the deck, and what the save
  loader does with an item type that no longer exists is a question about the
  engine nobody here has answered. They go once the migration has been seen to
  work in a real save. (`TREK_Helm.lua`, `TREK_HelmBackdrop.png` and
  `TREK_HelmEmblem.png` are the LCARS *panel* and are unrelated.)
- ~~**VHS tapes.**~~ Settled: the tape shelf at 2,0 (`LORE.md`).

---

## 9. The Starfleet refit (revision 35)

**Built 2026-09-30. Not yet seen in game.**

> *"when we first made this the shuttle interior was mostly vanilla parts and
> the owner Lucy Shepard lore explained she set it up that way on purpose. Now
> we have a much better art pipeline so we can and should make the interior
> much more starfleet looking like a real shuttle interior ... Our shuttle
> should still have a normal TV that shepard installed and the vhs tapes
> everything else should be starfleet styled"*

The cabin was a motel's carpet inside a gas station's walls, with a fridge
that had magnets on it, a hospital bed, three green lockers and two floor
lamps, and `LORE.md` 1a explained all of it: she collected them. The
Adirondack's art pipeline (`ADIRONDACK.md` 7) had since made fifty pieces of
Starfleet furniture that the game already loads, so the cabin is built from
those now, and the retcon is retired. **Two things aboard are not Starfleet's,
and both are Shepard's: her 1993 television and her tapes.**

The look is the runabout's aft cabin and the Type-9's (`design/art/shuttle_interior/reference_sheet.png`,
stills from TNG "Timescape", VOY "Threshold" and "Fury", and *Insurrection*):
warm grey padded bulkheads with a light strip, grey-blue carpet, LCARS panels
set into the walls, charcoal high-backed chairs, a biobed, and bunks built into
the bulkheads.

### 9.1 The deck plan

```
    0123
  0 KLVA      K bunk                    L Shepard's tapes, on a wall rack
  1 S*..      V her television, on a Starfleet cabinet    A the armoury
  2 G.h.      S stasis unit (the fridge)    G galley range (the oven)
  3 w.DH      w galley sink, and the rations in its cupboard
  4 M*.B      M the sick bay's cabinet    h the chair, facing the set
  5 R.@B      D warp core   H the Doctor   R replicator   B biobed   @ pad
```

**`tools/gen_shuttle_interior.py` is the plan.** It writes the `.tbx` (which
`TREK_InteriorLayout.lua` is checked against), draws the cabin from the real
tiles into `design/art/shuttle_interior/cabin.png`, and refuses a plan in which
a fitting cannot be reached. Look at the picture after any change.

Three rules decided where everything stands, and each came from getting it
wrong first:

1. **The camera sees two walls.** The game draws the cabin from the south-east,
   so only the bow (north) and port (west) bulkheads show their faces. The old
   three lockers stood against the starboard bulkhead facing west, and the room
   saw their backs -- which is what "blank green boxes" in the screenshot were.
   So everything tall stands against the bow or port wall; starboard has the
   machines and the biobed, which read from any side. The Adirondack's wall
   pieces come in `W` and `N` facings only for the same reason.
2. **Every fitting is worked from open deck.** The first draft of this plan
   had the range's front square under the chair, the sink's under the warp
   core, and the bunk boxed in by the television and the stasis unit -- the
   author spotted it from the mockup ("the warp core and chair and sink and
   oven are all right on top of each other?"). The whole x = 1 passage is open
   for the port wall's fronts, and y = 1 for the bow's; the core moved from
   1,3 to 2,3 (`C.DilithiumSpot`, `C.LegacyCoreSpot`) and the chair from 1,2 to
   2,2, which is also dead in front of the set. `tests/test_layout.py` walks
   it: every open square joined to the pad, every standing fitting's `Facing`
   square open, the biobed and the machines from any open side.
3. **Wall objects cost no floor.** The tape rack is a wall object, so 1,0 is
   deck -- which is how the bunk in the corner is reached.

### 9.2 What is where

| Square | Piece | Sprite | Tag | Holds |
|---|---|---|---|---|
| 0,0 | bunk (W) | `trek_adirondack_02_12` | `bunk` | -- (a bed, `averageBed`) |
| 1,0 | **tape rack** (N) | `trek_adirondack_02_214` | `tapes` | her tapes |
| 2,0 | **TV cabinet** (N) | `trek_adirondack_02_216` | `tvConsole` | nothing -- the player's |
| 2,0 | her television | `appliances_television_01_1` | `television` | |
| 2,0 | science display (N wall) | `trek_adirondack_02_177` | `console` | |
| 3,0 | arms locker (N) | `trek_adirondack_02_208` | `armoury` | the issue, as before |
| 0,1 | stasis unit (W) | `trek_adirondack_02_80` | `fridge` | nothing -- the player's |
| 0,2 | galley range (W), an `IsoStove` | `trek_adirondack_02_191` | `oven` | nothing -- the player's |
| 0,2 | wall display (W wall) | `trek_adirondack_01_40` | `console` | |
| 0,3 | galley sink (W), plumbed | `trek_adirondack_02_76` | `sink` | the 27 rations |
| 0,3 | wall sconce | `trek_adirondack_02_172` | `sconce` | |
| 0,4 | medical cabinet (W) | `trek_adirondack_02_120` | `medical` | the instruments |
| 2,2 | bridge chair (S-backed) | `trek_adirondack_02_89` | `chair` | |
| 3,4-3,5 | biobed (N) | `trek_adirondack_02_114`/`115` | `biobed` | -- (`goodBed`) |

Walls `trek_adirondack_01_0`/`_1`, the carpet `_24`, and **the pad `_27`**, a
transporter pad set into the carpet (`transporter_pad()` in
`tools/gen_adirondack_tiles.py`). The floor lamps are gone: the lights are
still hung by each client at `C.LampSpots`, and nothing stands there.

**Two new pieces, modelled in boxes** (`tools/shuttle_pieces.py`, rendered
by `gen_adirondack_furniture.py` as `kind = "boxes"`, appended to the end of
`adirondack_objects.py` so no existing tile moved -- `ADIRONDACK.md` 10.7):

- **the tape rack** -- two shelves of spines with her handwritten labels on a
  charcoal back plate. Its tile carries vanilla's metal wall shelf's
  properties (`furniture_shelving_01_28`/`29`): a wall object, attached to its
  wall, capacity 30, no `solid`.
- **the TV cabinet** -- a low console, and `Surface` 20 with `IsTable`,
  because the television is `IsSurfaceOffset` and is drawn at the height of
  what it stands on. A table's `Surface` is its top in 1x pixels (a 0.95
  counter is 35).

**The rations moved into the galley sink's cupboard.** Five player containers
became three (stasis unit, range, TV cabinet); the rations had to live
somewhere the camera sees, and a galley keeps its food in the galley. The
sink is both a container and plumbed, which the builder had never had:
`furnishAuthoredInterior` now gives a container its water store in the same
prepare, before the object is sent.

**The stasis unit cools.** `ItemContainer.isFridge` is the container type
string `fridge` and nothing else (bci 30-34), and the power bus powers it, so
it is the fridge by the engine's own test. It has no freezer.

### 9.3 The migration (`B.starfleetRefit`)

An old save's cabin is still standing, tagged, and `U.clearSquare` keeps
tagged things by design, so the new cabin would be built round the old one.
It runs once, as a build phase after the walls:

1. It notes every fitting tagged as the cabin's whose square-and-sprite is not
   in the new layout.
2. It furnishes the new cabin itself with stocking held off
   (`B.carryingOver`) -- the new armoury is to take the old one's contents, not
   a second issue on top of them.
3. It moves each old container's contents, the live items, into its successor
   (`B.CarryOver`: fridge -> stasis unit, oven -> range, the old rations
   locker -> the sink, armoury, sick bay and tapes to theirs). What has no
   successor -- the counters, the microwave -- goes onto the pad. A tape left
   in the old television is ejected onto the new rack with vanilla's own
   eject.
4. It takes the old fittings out, and the warp core's model off 1,3 (the
   crystals are ship state; only the model moves).

Floors and walls are swapped by their own phases. **`addFloor` never replaces
a floor**, so an old save's carpet is re-sprited in place the way vanilla's
shovel does it on the server (`setSprite`, `RemoveAttachedAnims`,
`transmitUpdatedSpriteToClients`); the walls come out once the new one on that
edge stands. Both touch only the sprites the cabin itself used
(`L.legacy`) -- a floor or wall a player laid is theirs.

**It waits for every square to be loaded, and the cabin is not current until
it has run.** And nothing is furnished while it waits: the first version let
the ordinary furnishing phase run in the meantime, which put a freshly stocked
armoury beside the old one -- the whole issue twice. The test that found it is
the one below; it had first been written to call the refit directly, which
could not see it.

`tests/test_multiplayer.py`'s `starfleet_refit()` builds an old save's cabin
from `tests/fixtures/TREK_InteriorLayout_rev34.lua` with today's builder,
fills its containers, and refits it: nothing of the old cabin left, each
player's thing in the right successor or on the pad, the armoury and the tapes
not issued twice, the tapes still recorded, the core moved, and the wait for
unloaded ground. `starfleet_refit_mp()` checks the floor swap reaches a client.
Fourteen mutations, one at a time, all caught -- two only after the test was
rewritten to build the whole cabin under a partial load.

### 9.4 The story

`LORE.md` 1a is rewritten: the cabin is standard issue and the television is
the one specimen she brought up. Log One's cabin section says so in the same
number of lines (so no line key moved), the first call's "every lamp" is her
television, Captain Titus is asked why there is a television in the shuttle,
and the Adirondack's crew tease Shepard about her television and her tape rack
rather than a fringed lamp and a fridge (`design/crew/bridge.txt`,
`engineering.txt`, `habitat.txt`). Log Six's moved chair is still the chair in
front of the set.

### 9.5 What to check in game

**In a fresh world:**

1. **The look.** Beam up. It should read as a Starfleet cabin with one 1993
   television in it. The TV should stand *on* its cabinet, not float over it
   or sink into it -- that is the `Surface` value.
2. **Walk it.** Every fitting from the square in front of it: the bunk from
   1,0, the rack from 1,0, the TV from 2,1, the armoury from 3,1, the galley and
   the cabinet down the x = 1 passage, the core from 1,3 or 3,3, the Doctor's
   square from 3,2.
3. **Sleep** in the bunk and in the biobed; **sit** in the chair and watch a
   tape.
4. **The galley**: the stasis unit keeps food cold, the range cooks, the sink
   runs, and the rations are in the sink's cupboard.
5. **The walls hold** (section 7, item 9) -- the Adirondack's bulkhead carries
   industry_01's properties, as the old walls did.

**In a save from before this** -- the part that most needs a real world:

6. Beam up. None of the old furniture anywhere, inside or outside the hull;
   whatever was in the fridge in the stasis unit, the oven's in the range, the
   old rations in the sink, the counters' and the microwave's on the pad; the
   armoury and the tape rack holding exactly what they held, not twice as
   much; the carpet and the pad swapped under your feet.
   `grep "refit:" console.txt` reports what it moved.
