# Working on this project

Orientation for anyone — human or agent — picking this up in a new session.

`README.md` says what the mod does. `DESIGN.md` says how to change the ship.
**This file says how to work on it without breaking it**, and most of what
follows was learned by breaking something.

This mod is a descendant of the TARDIS mod in `C:\Users\Arcade\tardis`. Its
engine helpers, its state handling and four of its five constraints came from
there, already paid for. The parts that are genuinely new — a multi-tile hull,
a footprint check, a transporter, an infinite-charge weapon — are where the new
mistakes live, and they are marked as such below.

---

## First five minutes

```sh
cd C:\Users\Arcade\pz_trekship
python tools/pzcatalog.py build                # ~10s, needed once per machine
python tools/luacheck.py TrekShuttle/42/media/lua
python tests/test_assets.py
python tests/test_stock.py
python tests/test_layout.py
```

If all five succeed you have a working setup. `test_layout.py` prints the cabin
floor plan with every fitting on it — the fastest way to see the shape of the
thing.

| Where | What |
|---|---|
| `C:\Users\Arcade\pz_trekship` | this repo |
| `C:\Users\Arcade\tardis` | the mod this one is built on; its DESIGN/DEV_GUIDE are worth reading |
| `C:\Program Files (x86)\Steam\steamapps\common\ProjectZomboid` | game install |
| `C:\Users\Arcade\Zomboid\mods\TrekShuttle` | where `tools/deploy.sh` installs to |
| `C:\Users\Arcade\Zomboid\console.txt` | the game log, **overwritten each launch** |

Target is **build 42.20.4**. Single player only.

---

## The loop

```sh
# 1. edit, then always:
python tools/luacheck.py TrekShuttle/42/media/lua
python tests/test_assets.py && python tests/test_stock.py && python tests/test_layout.py

# 2. install
sh tools/deploy.sh

# 3. run it
"/c/Program Files (x86)/Steam/steamapps/common/ProjectZomboid/ProjectZomboid64.exe" -debug

# 4. read what happened
sh tools/readtest.sh
```

**Mod Lua only loads when a world starts**, not at the main menu, and it is
only re-read on game restart. There is no hot reload. Every code change needs a
full restart.

The static checks take seconds; a game round trip takes minutes and needs the
user. Never skip step 1 to save time.

---

## Rules that exist because they were broken

### Verify engine methods before calling them

```sh
python tools/pzapi.py zombie.iso.IsoGridSquare isFree
python tools/pzapi.py zombie.inventory.ItemContainer Recurse
```

The game ships no `javap`; `tools/pzapi.py` parses the class files out of
`projectzomboid.jar` directly. **Use it.** In the TARDIS this cost a whole
session (`props:UnSet` for `props:unset`, throwing once per square).

### Prefer the overload that says what it does

`getItemsFromFullType(String, boolean)` and `getAllTypeRecurse(String)` both
exist and both return an `ArrayList`. The first one's boolean is undocumented.
Guessing at an undocumented flag is exactly how a feature ends up silently
doing nothing — and "the phaser never recharges" would look identical to "the
phaser recharges fine" until somebody actually ran dry.

The phaser uses `getAllTypeRecurse`, and `TREK_Phaser()` from the debug console
reports how many phasers the sweep can *see* as well as how many it charged,
so a lookup that finds nothing is visible rather than silent.

Note the pair, too: `getAllTypeRecurse` compares the **bare** type the way
`containsTypeRecurse` does, not the full id. Hand it `C.PhaserType`, then
filter on `C.PhaserItem`.

### A nil from `U.try` does not mean "no"

`U.try` returns `nil` when the call **fails** and `nil` when the call
legitimately returns nothing. Any probe that treats `nil` as an answer will
read a thrown exception as that answer.

This matters most where the answer authorises something. `squareIsClear`
returns the string `"ok"` for a clear square precisely so that a probe which
threw cannot be mistaken for clear ground to land a ship on:

```lua
local why = U.try("squareIsClear", function()
    if not sq:getFloor() then return "void" end
    ...
    return "ok"
end)
if why == "ok" then return true, nil end
return false, why or "engine"
```

### Batch anything repeated per square

A method that does not exist throws out of Java, and the engine dumps a full
stack trace **for every call**. In a per-square loop that is hundreds of dumps,
which locks the game hard enough to look like a crash.

```lua
local join = U.batch("light.lamppost")
for ... do join(function() cell:addLamppost(x, y, z, r, g, b, 8) end) end
```

`U.batch` stops after the first failure, logs one warning, and lets the pass
continue. **`U.try` is not a substitute.** It silences the *Lua* warning after
the first failure but keeps calling, and the engine keeps dumping a Java stack
trace every single time. `U.try` is for a call that happens once; `U.batch` is
for a call that repeats.

### Slice any search that touches thousands of squares

**New in this mod, and the one performance trap it has.**

The landing search covers a 49×49 area and asks about all fifteen footprint
squares at each position — about thirty-six thousand square lookups for one
pass. Written as a plain function called every tick, that is not slow, it is a
hard lock.

The job therefore keeps a cursor and does `SITES_PER_TICK` (48) positions per
tick, wrapping round when it runs out. It wraps rather than stopping because
ground that was not loaded on the first pass may well be by the third.

The same reasoning memoised `C.footprintOffsets()`. Anything walked inside that
loop must not allocate.

### Exempt the player's own square from the footprint check

**New in this mod, and it would have broken every landing.**

The hull is five tiles long. Anybody who right-clicks the ground in front of
them to call it down is standing *inside* the footprint, and anybody beamed to
a destination for the ship to follow them to is standing in the *middle* of it.
`sq:isFree(false)` is false for a square with a person on it, so without an
exemption the ship refuses every landing anyone ever orders — and the refusal
looks entirely plausible ("not enough room"), which is what makes it nasty.

`Core.roomToLand(cx, cy, z, exempt)` takes one square to ignore, and
`Core.exemptFor(player)` builds it. `Core.land` then steps the player clear as
the ship arrives.

### Never let a failure strand the player

**New in this mod.** A landing can fail, and the player has already been moved
to the site by then — that is the only way its chunks load at all. If the
search gives up, `TREK.Transport.recoverAboard` beams them back to the pad with
the reason.

The ordering is the design, not politeness. Check-then-move is impossible
because the ground cannot be inspected until somebody is standing on it;
move-then-fail without recovery leaves a character on foot a hundred miles from
their ship.

### Never build where no player is standing

Chunks only stream around a player. `getOrCreateGridSquare` on an unloaded
chunk returns an orphan square, and the first engine call touching it throws.
`U.square(..., create=true)` returns `nil` instead; `U.chunkLoaded` gates
everything. Arrival moves the player **first**, holds them safe, and builds once
the chunks appear.

**The same goes for removing things.** `U.square(x, y, z, false)` returns `nil`
for an unloaded chunk, and a function that reads that as "nothing there" is
wrong: it means "cannot tell yet". Return a reason, not a boolean, and write the
position down to retry — `s.ghosts` and `Core.sweepGhosts` are the pattern. In
the TARDIS, getting this wrong left a second police box at every place the ship
had ever been.

### One object per square, and prove it

`fit`, `line` and `place` claim the square they are about to use and refuse one
already taken. Overlaps do not fail on their own: `U.addObject` only looks for
its own sprite, so two objects stack, both are drawn, and which one is reachable
is a matter of draw order.

`tests/test_layout.py` catches this before the game runs, by parsing every
placement call out of `TREK_Build.lua`.

### Watch the taper

The hull cuts six squares off the bow and three off the stern. An offset that
is fine amidships is in open space at oy 3, and a placement that lands outside
the hull simply does not happen — no error, no object, nothing in the log. The
first draft of the layout had a toilet and two showers outside the ship and
looked completely fine in the source.

Add a fitting, then run `python tests/test_layout.py` and look at the picture.

### Tag every object you place

`U.clearSquare` keeps tagged objects and destroys untagged ones, so an untagged
shelf is wiped on the next rebuild. Tags also drive behaviour (`sink`,
`shower` and `toilet` get refilled) and the self-test counts fittings by tag.

### Never restock an existing container

The ship is meant to be lived in: what the player eats stays eaten.
`U.addContainer` returns a `created` flag; stock only when it is true.
Restocking an existing container does not refill it — it stacks a *second*
helping on the first, so loot multiplies with every rebuild.

### Bump `C.BuildRev` when generation changes

The cabin rebuilds lazily the next time somebody is aboard. Rebuilds preserve
furniture, container contents and dropped items. **Moving geometry is a
migration, not a rebuild.**

### Translations are one JSON file per category

Build 42 reads `media/lua/shared/Translate/EN/<Category>.json`, and the
category is part of the path, not the key. Item names go in `ItemName.json`
keyed by the bare full id (`"TrekShuttle.TrekPhaser"`), tooltips in
`Tooltip.json` keyed `Tooltip_*`, and only `IGUI_*` strings belong in
`IG_UI.json`.

An `"ItemName_TrekShuttle.TrekPhaser"` key inside `IG_UI.json` resolves to
nothing at all, silently — and it looks fine, because `DisplayName` in the item
script is the fallback the game shows when the lookup misses.
`tests/test_assets.py` checks all three files against the Lua and the scripts.

### The game runs Lua 5.1

Kahlua, where `unpack` is a global. `tools/luacheck.py` and the tests use Lua
5.5 and stub it back. Do not write `table.unpack` in mod code.

### Write Lua with the Write tool, not shell heredocs

This shell mangles quoted heredocs: an apostrophe in a comment or a `\n` in a
string will break or corrupt the file. Use `Write`/`Edit` for Lua, or a Python
script for surgical patches.

---

## Things that are true about the assets

Meshes and textures are **generated, never hand-authored**:

```sh
python tools/gen_shuttle.py TrekShuttle/42
python tools/gen_helm.py    TrekShuttle/42
python tools/gen_phaser.py  TrekShuttle/42
python tools/gen_poster.py  TrekShuttle/42
python tools/preview_model.py <mesh> <texture> out.png [yaw]
```

`preview_model.py` is a small software renderer — parser, z-buffer, per-pixel
texture sampling — so a model can be checked without launching the game. It
found four separate faults in the hull before the game was ever involved, and
every one of them was invisible in the source:

1. **The frame did not fit.** The previewer assumed a one-tile model, so a
   five-tile hull ran off every edge and could not be judged at all. It
   auto-fits now, and takes a yaw argument so both flanks can be seen.
2. **The hull was too flat.** Authored 3×5 tiles by 1.34 tall it read as a slab
   lying on the ground. The police box is 2.1 tall on a 0.9 base; anything much
   under 1.5 disappears into the ground plane.
3. **The starboard artwork was upside down.** `MeshBuilder.quad` maps its four
   points to fixed texture corners, so reversing the winding to turn a normal
   around also turns the artwork over. Pass the normal explicitly and keep the
   point order.
4. **The nacelles covered the registry.** They ran the full length of the hull
   at mid height, directly over the lettering and the cockpit glazing. The
   geometry was correct and the result was still wrong. **Render it and look.**

Two more things to remember: **Y is up** for PZ world models (Z-up lays the
hull on its side), and **1 unit is 1 tile**, with `scale` set in
`media/scripts/trekshuttle.txt`.

And one that is structural: **one texture region cannot be right on two
opposite faces.** It can be upright on both, or at the same physical end on
both, never both at once. The flanks have their own regions and
`mirror_region()` draws the second from the first.

---

## Failure signatures

Learn these; they map to causes that are not obvious from the symptom.

| What you see | What it usually is |
|---|---|
| **The ship never lands and never says why** | The landing job is still searching. It runs for `C.LandingTimeout` (420 ticks) before giving up. Check `[TREK] taking her down` in the log and wait for the verdict. |
| **"Not enough room" everywhere, even in a field** | The exemption is not being passed. `TREK_Room()` from the debug console reports the count and the first reason where you stand. |
| **The game locks up during a landing** | A search that is not sliced. See *Slice any search…* above. |
| **Black screen, character falling, game unresponsive** | An exception thrown inside a per-tick or per-square loop, flooding the log. Look for repeated stack traces in `console.txt`. |
| **The player falls on beaming aboard** | The cabin never finished building. Check for `arrival tick N: pad chunk loaded=false`. |
| **A fitting is missing and nothing is logged** | Either a sprite name that does not exist, or an offset outside the tapered hull. `tests/test_assets.py` catches the first, `tests/test_layout.py` the second. |
| **Two things on one square** | A placement that was not claimed, or a hand-placed object outside `fit`. `test_layout.py` catches it. |
| **A container is missing item types** | Container capacity. `AddItems` drops items silently once full. Use `U.stockEach`, which reads the container back and reports what did not land. |
| **The phaser runs out** | The sweep is not seeing it. `TREK_Phaser()` reports how many it found; zero while one is in your hands means the inventory lookup is wrong. |
| **The cabin looks like a hut in a forest** | The margin clearing did not run, or the chunks streamed in late. It re-runs on every rebuild. |
| **Two shuttles** | Something was removed at a position whose chunk was not loaded, and the failure was read as success. `TREK_Ghosts()` lists hulls known to be pending and forces a sweep. |
| **Half a feature works and the other half is silent** | A wrong engine call on the silent path. `grep -E "\[TREK\] WARN" console.txt` first, always — it is one line and it is the answer. |

---

## Testing

### Static, no game needed

| Check | Catches |
|---|---|
| `tools/luacheck.py` | Lua syntax, via a real Lua VM |
| `tests/test_assets.py` | sprites, items, meshes, textures, icons, the phaser's borrowed vanilla references, and every translation key |
| `tests/test_stock.py` | loot that does not spread across its list |
| `tests/test_layout.py` | fittings outside the hull or on top of each other; multi-tile offsets vs `SpriteGridPos`; the footprint against the mesh |

`test_layout.py` parses the layout back out of `TREK_Build.lua` with a regex.
That is less elegant than loading the module and it is not optional: the module
pulls in `Events`, `IsoObject` and the rest of the engine. If you add a new kind
of placement call, extend the regexes — the test fails loudly if it parses fewer
than 40 placements, precisely so a stale regex cannot quietly stop checking.

These have caught more real bugs than the in-game test has. Extend them in
preference to adding in-game checks.

### In game

Launch with `-debug` and load a **fresh** world; the self-test runs itself and
writes `TREK-TEST` lines. On a world where the ship is already in use it
deliberately stays out of the way — it beams the character across the map and
back, which is unwelcome mid-game.

| Console function | Does |
|---|---|
| `TREK_SelfTest()` | Force the whole run |
| `TREK_Rebuild()` | Tear down and regenerate the cabin, restocked. Stand aboard. |
| `TREK_Beam()` | Beam up if outside, down if aboard |
| `TREK_Room()` | Report whether the ship could land here and what is in the way |
| `TREK_Phaser()` | Report phasers found on you and recharge them |
| `TREK_Ghosts()` | List hulls waiting to be cleared and sweep up nearby ones |

### Watching the log

A `Monitor` on `console.txt` is useful, but **filter tightly**:

```sh
tail -F -n 0 "/c/Users/Arcade/Zomboid/console.txt" \
  | grep -E --line-buffered "TREK-TEST (FAIL|====)|\[TREK\] (WARN|cabin|shuttle|beam|no room)"
```

A broad filter like `TREK|ERROR` matches every frame of every Java stack trace
and will flood the conversation.

**Check the timestamp before drawing conclusions.** `console.txt` is
overwritten each launch, so `head -1` gives the session start time. Reading a
stale log and reporting it as the current run is a mistake worth avoiding.

---

## Working with the user

They run the game and report what they see; that is the only way most of this
gets verified. Practical notes:

- **Be explicit about what is verified and what is not.** Static checks passing
  is not the same as it working in game. Say which is which.
- **Warn before destructive rebuilds.** `TREK_Rebuild()` destroys container
  contents. Say so *before* they load in, not after.
- **They will spot real bugs from symptoms.** Investigate the report; do not
  explain it away.
- The cabin rebuilds **lazily on arrival**, so a change shows nothing until
  they beam aboard. Worth saying every time.

---

## Current state

Version **1.0.0**, build revision **1**.

**Verified by static checks only. Nothing in this mod has been seen in game
yet.** Everything below passes `luacheck`, `test_assets`, `test_stock` and
`test_layout`, and every engine method it calls was checked against
`projectzomboid.jar` with `pzapi.py` — but that is not the same as working, and
the distinction matters more here than usual because several of the mechanisms
are new rather than inherited from the TARDIS.

Highest-risk items, in the order they are worth checking in game:

1. **The hull model at 3×5 tiles.** No world model this large has been tried in
   either mod. It may be culled oddly, sorted wrongly against tiles it
   overhangs, or simply read as too big. `scale` in `trekshuttle.txt` is the
   dial.
2. **The phaser firing at all.** The whole ammunition argument in DESIGN.md is
   reasoning from the jar, not observation. If it will not fire, that is the
   first thing to look at.
3. **The landing search's cost in practice.** 48 positions a tick is a guess at
   a safe slice, not a measurement.
4. **The transporter's delayed job** interacting with the arrival hold in
   `TREK_Core`.
5. **`security_01` and `industry_01` sprite appearance.** They were chosen by
   name and properties from the catalogue; nobody has seen the cabin.

Inherited from the TARDIS and already proven there: runtime cell generation,
the arrival hold, chunk gating, the void margin, water refilling, the zombie
field, world-model placement, map picking, and the ghost sweep.

Known limits are listed at the bottom of `README.md`.

---

## Layout

```
TrekShuttle/42/media/lua/shared/TREK/TREK_Config.lua      all constants — start here
TrekShuttle/42/media/lua/shared/TREK/TREK_Util.lua        safe wrappers, state, geometry
TrekShuttle/42/media/lua/client/TREK/TREK_Build.lua       cabin construction, furnishing
TrekShuttle/42/media/lua/client/TREK/TREK_Core.lua        hull, landing room, hatch, field
TrekShuttle/42/media/lua/client/TREK/TREK_Transport.lua   the transporter
TrekShuttle/42/media/lua/client/TREK/TREK_Travel.lua      helm, courses, landing search
TrekShuttle/42/media/lua/client/TREK/TREK_Phaser.lua      keeping phasers charged
TrekShuttle/42/media/lua/client/TREK/TREK_Menu.lua        right-click menus
TrekShuttle/42/media/lua/client/TREK/TREK_SelfTest.lua    in-game step machine
```

Almost every change is `TREK_Config.lua` plus one `furnish` function.
