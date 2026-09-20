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
python tests/test_helm.py
python tests/test_multiplayer.py
```

If all seven succeed you have a working setup. `test_layout.py` prints the cabin
floor plan with every fitting on it — the fastest way to see the shape of the
thing.

| Where | What |
|---|---|
| `C:\Users\Arcade\pz_trekship` | this repo |
| `C:\Users\Arcade\tardis` | the mod this one is built on; its DESIGN/DEV_GUIDE are worth reading |
| `C:\Program Files (x86)\Steam\steamapps\common\ProjectZomboid` | game install |
| `C:\Users\Arcade\Zomboid\mods\TrekShuttle` | where `tools/deploy_windows.py` installs to (as `TrekShuttleDev`) |
| `C:\Users\Arcade\Zomboid\console.txt` | the game log, **overwritten each launch** |
| `C:\Users\Arcade\Zomboid\server-console.txt` | the local dedicated server's log |

Target is **build 42.20.4**: single player, hosted co-op **and dedicated
servers**, for anyone who subscribes on the Workshop. `MULTIPLAYER.md` is the
design and the record of what the engine actually does; read it before
changing anything that touches the world or the ship's state.

---

## The loop

```sh
# 1. edit, then always:
python tools/luacheck.py TrekShuttle/42/media/lua
python tests/test_assets.py && python tests/test_stock.py && python tests/test_layout.py && python tests/test_helm.py && python tests/test_multiplayer.py

# 2. install
python tools/deploy_windows.py

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

### The server owns the ship; a client asks

**The rule every other rule now sits under.** Build 42 loads `shared/`,
`client/` and `server/` Lua in *every* process -- single player, a co-op host,
a co-op guest, a dedicated server -- and the mod decides where each piece runs:

| Folder | Guard on line one | Runs in | Owns |
|---|---|---|---|
| `server/TREK/` | `if isClient() then return end` | single player, any server | the ship state, the cabin, loot, water, the hull, charges |
| `client/TREK/` | `if isServer() then return end` | single player, any client | UI, menus, **its own character**, the zombies it simulates, lights |
| `shared/TREK/` | none | everywhere | config, helpers, the protocol (`TREK_Net`), read-only world queries |

- **A client never writes the ship.** It reads `TREK.Ship.get()` and asks with
  `Core.send(player, "command", args)`; a handler in `TREK_Server.lua`
  validates it and calls `Ship.commit()`, which publishes the state.
- **A client moves only its own character**, and asks first
  (`Core.requestMove`), because a server with the speed anti-cheat rations
  long moves. Only a client can move an ordinary player at all.
- **The server changes the world only through transmit calls**:
  `transmitAddObjectToSquare` (object built complete first), `addFloor`,
  `transmitRemoveItemFromSquare`, `sendAddItemToContainer`,
  `AddWorldInventoryItem`. In single player the same calls act locally, so
  there is one code path for all three setups.
- **No admin-only or -debug-only calls** (see *The jar is not the API*).

`tests/test_multiplayer.py` runs the real Lua as single player and as a server
with two clients over a simulated network, and fails on a client edit, a
command with no handler, a missing guard, or any `WARN` the mod logs. The
local dedicated server (*Testing*, below) is how the engine side is checked.

### Verify engine methods before calling them

```sh
python tools/pzapi.py zombie.iso.IsoGridSquare isFree
python tools/pzapi.py zombie.inventory.ItemContainer Recurse
```

The game ships no `javap`; `tools/pzapi.py` parses the class files out of
`projectzomboid.jar` directly. **Use it.** In the TARDIS this cost a whole
session (`props:UnSet` for `props:unset`, throwing once per square).

### The jar is not the API

**This one cost three attempts and two trips into the game.** It is the single
most expensive mistake this project has made.

`tools/pzapi.py` reads `projectzomboid.jar`. A method being in the jar means
the *engine* has it. It does **not** mean Lua can reach it.

Only two things are reachable from Lua: methods on an object the engine handed
you, and globals. And the globals are `zombie.Lua.LuaManager$GlobalObject`
statics — nothing else. `zombie.inventory.InventoryItemFactory` is a real class
with a real `static CreateItem(String)` on it, `pzapi.py` shows it happily, and
in build 42 the Lua global is **null**:

```
[TREK] WARN (CreateItem:Base.Pistol) attempted index: CreateItem of non-table: null
```

Every container in the cabin was built perfectly and stocked with nothing, and
the only symptom was empty lockers. Use `instanceItem(id)` — it is a
`GlobalObject` static, and vanilla calls it in 187 places.

**So: before calling a global, grep the game's own Lua for it.**

```sh
PZ="/c/Program Files (x86)/Steam/steamapps/common/ProjectZomboid/media/lua"
grep -ran "instanceItem(" "$PZ" | wc -l          # 187 -- real
grep -ran "InventoryItemFactory" "$PZ" | wc -l   # 0 in practice -- not real
```

`pzapi.py` answers "does this method exist". Grepping vanilla Lua answers "may
I call it". **You need both, and the second one is the one that was skipped.**

**Two more ways a method in the jar is not usable, both learned in game:**

1. **It is private.** `pzapi.py` used to list every method unmarked; it now
   lists only public ones (add `--all` to see private ones, flagged). The
   sink's reserve-water methods are private and looked perfectly callable.
2. **It is public and refuses.** Build 42's `setGodMod`,
   `setZombiesDontAttack`, `setInvincible`, `setNoClip` and `setInvisible` all
   check the character's *role* for a capability first and silently do
   nothing without it -- which is every ordinary player. God mode during
   flight never worked. Worse, there is a route around the role check
   (`setGodModCheat`) that is gated on `Core.debug`: **it works under -debug
   and nowhere else**, so a test run passes and every Workshop player fails.
   `tests/test_multiplayer.py` fails if any of these setters is called again.

When a method's behaviour matters, read what it does, not just its name. The
game's own bytecode says which fields and capabilities a method touches; that
is how the role check was found.

**And design out the permission instead of fighting it.** Hands-on flight
tried to keep the pilot safe with those setters, then by holding the body in
mid-air; both failed in game, and flying a body at 90 tiles a second would be
kicked by the speed anti-cheat on any server. It was removed, and came back as
something the engine cannot argue with: the ship is a **vehicle**, a seat with
no door cannot be bitten, vehicles may travel fast, and no character is moved
at all. See `PILOTING.md`.

The same reasoning applies to *which* API a given object actually uses — see
*Two APIs for water* below.

### Never trust one way of doing it when the cost of being wrong is silence

`U.addVerified` tries `instanceItem`, then `container:AddItem(id)`, then
`InventoryItemFactory`, keeps whichever works, and logs which one it used. The
fallbacks cost two `pcall`s once per build. Being wrong cost two sessions.

The important half is not the fallbacks, it is the **proof**: it counts the
container before and after and only reports success if the contents actually
grew. Every one of those three paths can fail silently — a nil back, a throw
swallowed by `pcall`, a full container dropping what it was handed — and from
Lua they all look identical. Counting is the only answer that cannot lie.

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

`TREK.World.roomToLand(cx, cy, z, exempt)` takes one square to ignore, and
`World.exemptFor(player)` builds it. The client steps the player clear when the
server replies `landed`.

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

Chunks only stream around a player -- on the server as much as on a client.
`getOrCreateGridSquare` on an unloaded chunk returns an orphan square, and the
first engine call touching it throws. `U.square(..., create=true)` returns
`nil` instead; `U.chunkLoaded` gates everything. Arrival moves the player
**first** and holds them on the pad; the client reports `boarded`, and the
server builds once the cabin's chunks are loaded around them there.

**Beaming down follows the same rule.** The transporter used to look for clear
ground at the destination *before* moving -- and far from the ship nothing is
loaded, so it found none. It now materialises the player first and settles
them on the nearest clear square once the ground streams in.

**The same goes for removing things.** `U.square(x, y, z, false)` returns `nil`
for an unloaded chunk, and a function that reads that as "nothing there" is
wrong: it means "cannot tell yet". Return a reason, not a boolean, and write the
position down to retry — `s.ghosts` and `TREK.Server.sweepGhosts` are the pattern. In
the TARDIS, getting this wrong left a second police box at every place the ship
had ever been.

### A hook on a toggle must ask before it calls through

**New in this mod, and it hid a whole feature in plain sight.**

Vanilla's `ISVehicleMenu.showRadialMenu` is a *toggle*. Its first act is
`menu:clear()`, and then:

```lua
if menu:isReallyVisible() then ... menu:undisplay() return end
```

So `isReallyVisible()` is true only on the press that **closes** the menu. And
it is false on the press that opens it, because `addToUIManager()` reaches
`UIManager.AddUI`, which appends to the pending `toAdd` list, while
`isReallyVisible()` asks whether the element is in the **live** `getUI()` list.
It only becomes true a frame later.

A wrapper that added its slices behind `if not menu:isReallyVisible() then
return end` therefore ran at no useful moment at all: never on open, and on
close only after vanilla had already cleared and dismissed the menu. The
shuttle's *Go aboard* and *Take her up* were never added in any build, and from
inside the game flight simply looked broken.

**Take the reading you need before calling the original, not after** — by then
the state has flipped either way:

```lua
local closing = menu ~= nil and menu:isReallyVisible()
baseRadial(playerObj)
if closing then return end
```

`tests/pz_sim.lua` models the radial menu as the toggle it is, including the
one-frame delay before it is really visible, and `tests/test_multiplayer.py`
opens it for real and reads its slices back. Mutation-check that test if you
touch it: with the old guard it must report only vanilla's two slices.

### A vehicle's altitude is a floor, not a height

**New in this mod, and it disproved a whole design before it was written.**

Raising a vehicle's physics body does not put it in the air.
`BaseVehicle.update()` sets `setZ(0.0f)` **unconditionally** every tick, then
restores the physics level *only* if a floor tile exists under the vehicle's
centre square at that level or the one below:

```java
setZ(0.0f);                                              // bci 1429
int lvl = PZMath.fastfloor(jniTransform.origin.y / 2.4494900703430176f + 0.05f);
if (sq != null && (sq.getFloor() != null || (sqB != null && sqB.getFloor() != null)))
    setZ((float) lvl);                                   // bci 1530
```

Rendering, the crew's drawn position, collision, world damage and every other
client all read that clamped `getZ()`. Lift the body with nothing under it and
you get a ship that flies in Bullet and sits on the road in the game, mowing
down fences — *present, drawn, and inert*, the same shape as the three bugs
above it in this file.

So flight is **driving on an invisible floor**: `invisible_01_0` is a vanilla
tile whose only properties are `attachedFloor` and `solidfloor`.
`TREK_Sky.lua` lays it around the ship, and everything else is vanilla's own
vehicle code, untouched.

Two things this cost that are worth keeping:

- **The bytecode is the documentation.** `tools/pzapi.py` says a method exists;
  `tools/javarefs.py` says what it touches; only a real instruction-level
  disassembly says *under what condition*. `javarefs` lists references in
  bytecode order with no branches, so it cannot tell you that `setZ(0)` is
  unconditional and the one after it is not.
- **The exposure allow-list is knowable.** `LuaManager$Exposer.shouldExpose` is
  strict `exposed.contains(c)` over an explicit list built in `exposeAll()`.
  If a class is not in that list, no amount of it being public matters. That is
  the definitive answer to "can Lua touch this", and it is worth grepping
  before designing around any engine type.

### The black outside the cabin is a map, not a clearing

The cabin's cell is off the vanilla map, and build 42's world generator fills
any cell with no map data -- grass, trees, zombies. Clearing that at runtime
never fully works: the view reaches past any margin, chunks stream in late,
and zombies walk in. The user compared it with the Fifth-Wheel RV interior,
which is black outside, and that mod's answer is the right one: it ships a map
whose cells are **empty**. A mapped cell is never generated, and a map cell
with no tiles renders as nothing.

`tools/gen_void_map.py` writes `media/maps/TrekShuttle`: the interior cell and
two rings of cells around it (5x5; one ring left trees in view from the
cabin's height) as empty cells (the format is documented in the script;
the output is byte-identical to the RV's empty cells). `tests/test_assets.py`
reads every file back. If `C.InteriorCell` ever moves, regenerate.

- Single player (`Map=DEFAULT`) and the in-game Host settings add a mod's map
  folders automatically. A dedicated server's `.ini` must list it:
  `Map=TrekShuttle;Muldraugh, KY`. The server logs whether it is loaded.
- A map only affects cells never visited: an existing save that already
  generated the cabin's surroundings keeps them. The runtime clearing stays as
  the fallback for that case.

### The interior is authored in BuildingEd, not in the code

`server/TREK/TREK_Build.lua` builds the deck, walls, lamp fittings and the
helm item.
**Everything else — every fitting, every locker — comes from
`design/buildinged/TrekShuttle_Interior.tbx`** and is read at runtime out of
`TREK_InteriorLayout.lua`. To move a locker, open the map editor, not the Lua.

Layering on one square is deliberate here (a counter with a microwave on it, a
console over a desk), so `furnishAuthoredInterior` bypasses the `claim()` check
that the lamps use. It is only `tests/test_layout.py` that would notice a
lamp (`C.LampSpots`) landing on top of a locker.

**Dead placement code is worse than none.** For a while every `furnish*`
function in `TREK_Build.lua` was unreachable — the BuildingEd switch had
replaced them — and `test_layout.py` was busy validating *those* offsets. It
drew a confident picture of a ship that no longer existed and passed while the
real interior went unchecked. If a furnishing function stops being called,
delete it, and check what the tests are actually reading.

### Verify a placement against the layout, not the source

A placement outside the hull simply does not happen — no error, no object,
nothing in the log. An early draft had a toilet and two showers outside the
ship and looked completely fine in the source.

`tests/test_layout.py` loads `TREK_InteriorLayout.lua` for real (it is pure
data — no engine calls — so it can be `require`d under lupa) and prints the
deck plan with every fitting on it. Run it and **look at the picture**. It also
checks the Lua against the `.tbx` it came from, so a locker added in the map
editor and not carried across fails rather than quietly never appearing.

### A comment is not a container: check what the sprite actually is

**New in this mod, and it put the whole drinks cabinet in the oven.** The
layout entry read

```lua
-- The galley's drinks cabinet: raktajino and Earl Grey to hand, the ale
-- and the bloodwine behind them.
{ x = 0, y = 5, sprite = "appliances_cooking_01_40", tag = "drinks", ... },
```

and `appliances_cooking_01_40` is `CustomName = Oven`, `IsoType = IsoStove`,
`container = stove` — the lower half of a two-tile oven, `SpriteGridPos 0,1`
to its twin's `0,0`. Everything passed: the sprite exists, it really is a
container, the `.tbx` really does place it there, the loot list really does
exist. The only thing wrong was that it was an oven, and the only place it
said "cabinet" was a comment.

Geometry belongs to the `.tbx` and `tag`/`loot` belong to us, so this class of
mistake is always ours: **we chose which fitting the loot hangs on.** Before
naming one, look it up —

```sh
python -c "import json; print(json.load(open('tools/_catalog/tiles.json'))['tiles']['appliances_cooking_01_40'])"
```

`CustomName` is what the player sees when they open it. `tests/test_layout.py`
checks that a stocked entry *can* hold things and that the Lua matches the
`.tbx`; nothing can check that a stove is a sensible home for bloodwine, so
that one is on whoever writes the entry.

Two smaller things this turned up, both fixed:

- **A layered square hides a glyph.** The deck plan draws one glyph per square,
  so loot put on the counter at `1,0` would have vanished behind the sink's
  `w`. If a fitting is worth a glyph, put it somewhere the plan can show it.
- **A hard-coded list of loot lists goes stale.** `tests/test_stock.py` named
  its eight lists in a tuple, and `drinks` — the newest list in the ship — was
  never added, so the one that most needed checking was the one nothing
  checked. It reads the names out of `TREK_InteriorLayout.lua` now.

### Tag every object you place

The server build's `clearSquare` keeps tagged objects (and the deck floor)
and destroys untagged ones, so an untagged shelf is wiped on the next rebuild.
Tags also drive behaviour: `sink`, `shower` and `toilet` get water.

### Sink water: give the fixture a water store -- nothing else works

**This section has been wrong twice.** First it said a sink's water was
*reserve* water (`setReserveWaterAmount`): those methods are **private**, nil
from Lua, and the top-up threw on every refill. Then it said to call
`createFluidContainersFromSpriteProperties()`: **that method is empty** in
build 42. Both passed the in-game water test, because a fresh world's mains
were on.

What works is what vanilla's own `addWaterContainer` command does, and the
server build does it to each plumbed fixture before sending it:

```lua
local f = ComponentType.FluidContainer:CreateComponent()
f:setCapacity(C.WaterCapacity)
f:addFluid(FluidType.Water, C.WaterCapacity)
GameEntityFactory.AddComponent(obj, true, f)
```

Top-ups use `obj:addFluid(FluidType.Water, n)`, which syncs itself on a server;
the server refills every game minute. A fixture from an older build with no
store is removed and placed again with one -- the only way every client is
sure to get the new component.

The game's own "infinite water" (`isWaterInfinite`) needs the square to be in
a *room* with the mains on; the cabin has no rooms, so it never applies.

**To test water honestly, turn the mains off**: sandbox *Water Shutoff* set to
instant. `TREK_Water()` logs each fixture's capacity, amount and `hasWater`.

### Containers built at runtime are not containers

A sprite being a container in the tileset is not enough. A map-loaded object
gets its `ItemContainer` for free; one built at runtime does not, and
`obj:createContainersFromSpriteProperties()` is what makes the difference.
The server build calls it on the new object, stocks it and marks it explored
**before** sending it, so the object reaches clients with its contents -- and
without `setExplored(true)` vanilla rolls its own loot into it on first open.

Without it the locker is placed, drawn, and cannot be opened, and it looks
exactly like a stocked one. `TREK_InteriorLayout.lua` marks every stocked entry
`container = true`, `TREK_Build` also treats any entry carrying `loot` or
`special` as one so a forgotten flag cannot repeat it, and
`tests/test_layout.py` cross-checks the flag against the tile catalogue **both
ways** — a stocked entry whose sprite cannot hold anything fails, and so does a
container sprite that nothing stocks.

### Stock containers by weight, not by item count

Item count says nothing about how full a container looks. A locker holds 40
units, a microwave 5 — `amount = 8` heaps the microwave and leaves the locker
at a fifth. `U.fill` reads `getCapacity()` off the object and fills to
`C.FillFraction` of it, so every fitting the map editor drops in ends up
looking the same whatever size it is.

`C.FillItemCap` bounds the item count, because the lightest lists cannot reach
the target any other way: a bandage is 0.1 of a 40-unit locker, so half a
locker of dressings is two hundred items. When a list is too light to make the
target at a sane count, **put heavier things in the list** rather than raising
the cap — a sick bay stocked with kits, boxes and splints is both better
loot and better reading than one holding ninety bandages.

`python tests/test_stock.py` prints the fill each container size reaches.

### A weapon model is a static mesh, and Y is up

**This one hid four weapons behind a wrong comment for months.** The phaser's
note in `trekshuttle.txt` used to say a custom `WeaponSprite` "needs a rigged
attachment set rather than a static mesh". It does not, and believing it ruled
the whole blades section off the roadmap.

`WeaponSprite` names a `model` block exactly as `StaticModel` does; the block
names a mesh and a texture; the swing comes from `SwingAnim`, a string
resolved against the game's own **global** animation set. No bones, no
skinning, no animation files. Vanilla's `Katana` model block is four lines.

- The animation set is closed — `Bat`, `Stab`, `Heavy`, `Spear`, `Throw`,
  `Rifle`, `Handgun`, `Stone`, `Shove` — and a name outside it silently does
  not animate. `tests/test_assets.py` checks `SwingAnim` and `WeaponSprite`
  against the game's own scripts.
- **A weapon model must be declared in `module Base`.** `WeaponSprite` does
  *not* resolve inside the mod's own module the way `StaticModel` does, so the
  hull and the helm draw fine from `module TrekShuttle` and a weapon there
  draws nothing at all. The tell in the log is the engine trying to load the
  **model block's name** as a mesh path — `Failed to load asset:
  AssetPath{ "TrekBatlethModel" }` — which it only does when the name matched
  no `ModelScript`. Every vanilla weapon model lives in `module Base`, so
  `media/scripts/trekweapons.txt` does too, beside the item that stays in the
  mod's module and names it bare. No vanilla script file declares two modules,
  hence the second file. `test_assets.py` records each model's module and
  fails a `WeaponSprite` pointing outside `Base`.
- **Weapon meshes are Y-up.** The hull and the helm are Z-up, so this is the
  opposite of every other mesh here. `MeshBuilder.place()` maps
  *(east, north, height)*, which is the right helper for something standing on
  the ground and the wrong one for a blade: going through it authored the
  bat'leth lying flat with its thickness pointing at the sky. `gen_batleth.py`
  writes vertices in the model's own named axes instead. **The preview caught
  that in one render and the source never would have.**
- The two attachments, `Bip01_Prop2` (in the hand) and `world` (on the
  ground), are **optional** — omit them and the engine uses a default. Their
  offsets can only honestly be set by looking at the weapon in a fist.
- Where a blade *hangs* when slung is not on the weapon model at all. The
  item's `AttachmentType` routes through `ISHotbarAttachDefinition.lua` and
  `AttachedLocations.lua` to an attachment on the **character** model.
- **The mesh's own dimensions are its size in game; `WeaponLength` is a reach
  stat and scales nothing.** And the bracket to sit in is not the one you would
  guess: measure vanilla and every weapon in build 42 is a thin vertical line —
  a machete is 0.009 wide by 0.335 long, and the widest mesh in the entire
  arsenal is the canoe paddle at 0.123 across. A bat'leth is the shape this
  engine has never drawn, a crescent worn and swung *across* the body, so its
  full span reads as width where a bat of the same real length reads as a
  stroke. Real-world scale is not the test; the sprite is. Check the **bounding
  box**, not the constant you set — the bat'leth's arc bulges past its own
  chord, so `SPAN = 0.46` drew 0.531 across, wider than a baseball bat is long.
- **An item with an `AttachmentType` needs a 32×32 icon, not 64×64.** It is the
  only kind vanilla's hotbar draws, and `ISHotbar.lua:52` places it at
  `slotX + tex:getWidth() / 2` — the slot's left edge plus *half the texture's
  own width*, which only centres when the texture is half the 60px slot. A 32px
  icon occupies 16–48; a 64px icon occupies 32–96, starting at the middle of
  its own slot and running 36px into the next one. (The `y` on that same line
  centres properly, so the symptom is an icon that is correct vertically and
  shoved right — and three rounds of shrinking the drawing *inside* a 64px
  frame could not touch it, because the frame was the fault.) Every other icon
  here is 64×64 and right: nothing else attaches. `test_assets.py` enforces it.

### A drink is a fluid, and a modded fluid is a string

A build 42 drink is a `fluid` block plus a vessel item with a
`FluidContainer`. The fluid carries every effect, so a `ThirstChange` on the
*item* is ignored — silently.

- A mod may declare `fluid` blocks in its **own** `media/scripts`. Vanilla's
  all sit under `scripts/generated/`, which makes it look generated-only.
- **`FluidType` is a fixed Java enum**; every modded fluid is
  `FluidType.Modded`, so `FluidType.<yourname>` is nil. The handle from Lua is
  `Fluid.Get("<name>")`. `addFluid` takes a `String`, a `FluidType` or a
  `Fluid`.
- **`ColorReference` is fatal if it is wrong.** Not a warning, not a black
  drink: `FluidDefinitionScript.getColor` throws `Cannot find color: X`, which
  aborts `ScriptManager.loadScripts`, and the world refuses to load with
  "there are script load errors". Use only a colour a vanilla fluid already
  uses -- `tests/test_assets.py` enforces that -- because a name being a string
  inside `Colors.class` does **not** make it a registered colour. That is "the
  jar is not the API" one level down, and it cost a crash.
- The `Fluids { }` block inside the component is a **whitelist**: without it
  the vessel refuses the drink it was made for.
- Fluid names live in `Translate/EN/Fluids.json`, their own category file.

### A generated background is not the colour you asked for

**New in this mod, and it produced four finished-looking icons that were
wrong.** `tools/key_icon.py` keyed on a hard-coded `#FF00FF`. Ask an image
model for flat magenta and it returns something *like* magenta -- the drinks
came back on a dusty raspberry around `(206, 34, 137)`, about 130 away -- which
the fixed key read as foreground. Every icon kept its background as an opaque
dark red square and looked merely muddy.

The key colour is now **measured** from a border ring, reported, and the
result counted: `key_icon.py` refuses to write a file when less than a quarter
of the frame keyed out. Same lesson as `U.addVerified` and `B.stockReport` —
*read the result back*, because every way this fails produces a plausible file.

### Source art lives in `design/art/`, not just in `media/textures/`

**Undocumented until it was got wrong.** `media/textures/Item_*.png` is the
64x64 *output*. The 1024px generated original, and the contact sheet it was
judged on, belong in `design/art/<category>/`:

```
design/art/food/raktajino_raw.png        the generated original, pre-keying
design/art/food/drinks_sheet.png         what it was vetted on
design/art/weapons/batleth_raw.png
design/art/weapons/preview_batleth.png   mesh renders, flat on and edge on
design/art/helm/vet_emblem.b64           what was sent to analyze-image
```

`design/` is neither deployed nor packaged, so this costs the Workshop build
nothing. Keep the raws: re-keying an icon or re-running a critique needs the
original, and regenerating it gets a *different picture*, not the same one
again. Newer raws are `.png` rather than `.jpg` on purpose -- JPEG ringing
around the key colour fights the alpha ramp.

### Vet icons with `tools/vet_icons.py`, at 32px, against the rest of the set

```sh
python tools/vet_icons.py design/art/food/drinks_sheet.png Raktajino EarlGrey
python tools/vet_icons.py design/art/all_icons.png          # every icon
```

Two rows, 64 and **32**, on the inventory's dark grey. The small row decides
it. Then hand the sheet to the Gemini toolkit's `analyze-image` and ask for a
critique of that row -- that pass is what caught the bloodwine bottle
disappearing into the background and the raktajino reading as an empty hole.

**Render the whole set, not just the new icon.** A new icon judged on its own
passes easily; put beside the other eleven it can be obviously wrong. The
bat'leth looked acceptable alone and was plainly the weakest thing on the
sheet next to the food -- thin and wiry where everything else is chunky.

### An icon can be rendered from the model instead of drawn

The image model is the default (ROADMAP.md, "How art gets made") and is right
for food, where there is no mesh. For something the mod already has geometry
for, `tools/preview_model.py` will render the icon instead -- `gen_batleth.py`
does, and `gen_phaser.py` draws its own procedurally.

Two goes at describing a bat'leth to an image model produced a curved sword
with a hilt, and then a featureless arch. It is an awkward shape to write down
and a trivial one to render. The real win is that the icon is then the **same
object** as the in-hand model, from the same mesh and texture, so the two
cannot drift apart.

`preview_model` draws on a flat `(28, 30, 36)` with no antialiasing, so key
that background by **exact match**, not with `key_icon.py`'s colour ramp: the
bat'leth's grip leather is only 33 away from it, well inside the distance the
ramp treats as backdrop, and the three hand bindings would have been erased.
Tilt the result if the object is long and thin -- a square icon holding a 2.3:1
crescent is mostly empty, which is why vanilla draws its blades on the
diagonal.

### Item icons: generate on magenta, key it, vet it at 32px

Image models paint backgrounds; they do not emit alpha. So every icon is
generated on flat `#FF00FF` and `tools/key_icon.py` turns it into a 64x64
transparent `media/textures/Item_*.png`: soft alpha from the distance to
magenta, then a full de-spill so no pink survives (the stew's steam came back
lilac until it did). Nothing in this mod is meant to be pink; an icon that
genuinely needs magenta should be generated on a different key colour.

**Vet at 32x32, on the dark inventory background.** Detail that sells an image
at 1024 is mush at 32. The first gagh was a lovely bowl of worms and read as
chili in the inventory; the fix was fewer, fatter, lighter worms spilling over
the rim. Big simple shapes and strong contrast survive the shrink.

Borrow vanilla world and hand models where an item's shape already exists
(bowls, bars) -- `test_assets.py` checks every borrowed name.

### Never restock an existing container

The ship is meant to be lived in: what the player eats stays eaten.
The build's `place()` returns a `created` flag; stock only when it is true.
Restocking an existing container does not refill it — it stacks a *second*
helping on the first, so loot multiplies with every rebuild.

A container is stocked **once, ever**: when it is made, or when it has never
been stocked (no `TREKStockRev` in its mod data) and is still empty -- the
repair path for saves left behind by the builds that could not create items.
The rule used to be "restock when the revision differs", which would have
doubled every locker in every save on the next `C.BuildRev` bump.

The consequence to remember: **new loot never reaches an existing save.** Test
new items in a new world, or hand them over from the debug console
(`TREK_Galley()` for the food).

### Bump `C.BuildRev` when generation changes

The cabin rebuilds lazily the next time somebody is aboard. Rebuilds preserve
furniture, container contents and dropped items. **Moving geometry is a
migration, not a rebuild.**

### UI runs every frame: test it before the game does

`prerender` and `render` run sixty times a second, so one nil in them is not
one error but a stack trace per frame for as long as the panel is open. And a
label that runs off its button can otherwise only be seen in game.

`tests/test_helm.py` drives the real `TREK_Helm.lua` against stubs of
`ISPanelJoypad`, `ISButton` and friends that record every draw call, and fails
on a throw, a draw outside the panel, a label wider than its button, a
control that asks for nothing, or a button a controller cannot reach.
`tools/preview_helm.py` replays the same draw calls into a PNG with the real
textures. **Look at the render**: it found a clipped course line that every
test passed.

Two things the harness taught:

- **Compare Lua tables in Lua.** lupa hands Python a fresh proxy on every
  access, so `a != b` in Python is always true. Use `rawequal` inside Lua.
- **Mutation-check a new test.** Break the code on purpose and confirm it
  fails before trusting a first-time pass.

### Every panel must work with a controller

The Steam Deck runs PZ with a gamepad. Derive panels from `ISPanelJoypad`,
register every button with `insertNewLineOfButtons` / `insertNewListOfButtons`,
put close on B with `setISButtonForB`, draw a visible focus state (there is
no pointer), and give anything that needs a mouse click a controller route --
the helm's map crosshair is the pattern. Hand focus back on close
(`setJoypadFocus`), or the controller is left driving a panel that is gone.

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
python tools/gen_batleth.py TrekShuttle/42   # mesh, texture and icon
python tools/gen_poster.py  TrekShuttle/42
python tools/preview_model.py <mesh> <texture> out.png [yaw]
python tools/vet_icons.py design/art/all_icons.png    # icons at 32px
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
| **A fitting is missing and nothing is logged** | Either a sprite name that does not exist, or an offset outside the hull. `tests/test_assets.py` catches the first, `tests/test_layout.py` the second. |
| **Two things on one square** | A placement that was not claimed, or a hand-placed object outside `fit`. `test_layout.py` catches it. |
| **Every container in the cabin is empty** | Items are not being created. `grep "CreateItem\|stocking containers via" console.txt` — the second is logged once per build and names the path that worked. See *The jar is not the API*. |
| **One container is empty and the rest are fine** | Either its sprite is not a container in the tileset, or its `loot` names a `C.Loot` list that does not exist. Both fail in `test_layout.py`; in game, `TREK_Stock()` names the square. |
| **Loot is stocked, but in the wrong piece of furniture** | The entry's `loot` is hung on a sprite that is not what the comment beside it claims. Look the sprite up in `tools/_catalog/tiles.json` and read `CustomName`. No test can catch this one. |
| **A container is missing item types** | Container capacity. `AddItems` drops items silently once full. Use `U.stockEach`, which reads the container back and reports what did not land. |
| **A weapon is equipped and the hand is empty** | `WeaponSprite` names no model, the model block is not in `module Base`, or the mesh/texture is not on disk. `tests/test_assets.py` checks all four. The log names the model block itself as the failed asset when the module is wrong. |
| **A weapon swings with no animation** | `SwingAnim` is not one of the nine names vanilla uses. |
| **A weapon is twice the size of the character holding it** | The mesh's own dimensions are its scale; `WeaponLength` changes nothing. Read the **bounding box** the generator prints, not the span constant — an arc bulges past its chord. Vanilla's widest weapon mesh is 0.123 across. |
| **An icon overlaps the next hotbar slot** | Its item has an `AttachmentType` and a 64×64 icon. Vanilla's hotbar assumes 32×32; see *A weapon model is a static mesh*. |
| **A drink has no effect, or the wrong one** | The effects are on the *fluid*, not the item; a `ThirstChange` on the vessel is ignored. `Fluid.Get("name")`, never `FluidType.<name>` -- a modded fluid is `FluidType.Modded`. |
| **A vessel will not accept its own drink** | The `Fluids { }` whitelist inside its `FluidContainer` is missing or names the fluid wrongly; the log says `Cannot find fluid`. |
| **A new icon looks muddy, with a dark square behind it** | The generated background was not the magenta that was asked for, so it keyed as foreground. `tools/key_icon.py` now measures the key and refuses to write; re-run it and read the line it prints. |
| **A container looks under-stocked** | Its list is too light to reach `C.FillFraction` before `C.FillItemCap` binds. Put heavier items in the list; `tests/test_stock.py` prints what each size reaches. |
| **The sink runs dry after a few weeks** | The fixture has no water store of its own and was living on the mains. See *Sink water*. `TREK_Water()` shows capacity 0. |
| **It works for the host and not for anyone else** | Something is being done on a client that only the server may do, or only locally. `tests/test_multiplayer.py` should catch it; if it did not, add the case. |
| **"The transporter is recharging"** | Working as designed on a server whose `AntiCheatSpeed` kicks or bans: 3 beams, one back every 150 s. `TREK_Charges()` reports it. |
| **"You are not on this shuttle's crew"** | Sandbox *Who may use the shuttle* is *Owner and crew*. The owner or an admin adds crew from the aboard menu. |
| **Stuck on the pad, then put back outside** | The server never reported the cabin ready. Look for `[TREK] cabin ready` in the server's log and `arrival tick` lines on the client. |
| **The phaser runs out** | The sweep is not seeing it. `TREK_Phaser()` reports how many it found; zero while one is in your hands means the inventory lookup is wrong. |
| **Grass, trees or zombies outside the cabin** | The void map is not loaded (server log: `the 'TrekShuttle' map is not loaded` -- add it to `Map=`), or the save visited that area before the map existed. Test in a new world. |
| **Two shuttles** | Something was removed at a position whose chunk was not loaded, and the failure was read as success. `TREK_Ghosts()` lists hulls known to be pending and forces a sweep. |
| **The shuttle "flies" but is drawn on the ground** | Its z is not its physics height. `BaseVehicle.update()` zeroes a vehicle's z every tick and restores the level only where a floor exists under its centre square — so the sky plane is not being laid. `grep "sky plane" console.txt`. See *A vehicle's altitude is a floor, not a height*. |
| **The shuttle flies and ploughs through fences** | Same cause. Collision resolves at `getZ()`, which is 0 without a floor. |
| **A ship parked in the sky for ever** | Flight ended without `Sky.clear()`. The floors are world objects and they are saved. `s.skyAt` is how they get lifted; if that was lost, they are permanent. |
| **Half a feature works and the other half is silent** | A wrong engine call on the silent path. `grep -E "\[TREK\] WARN" console.txt` first, always — it is one line and it is the answer. |

---

## Testing

### Static, no game needed

| Check | Catches |
|---|---|
| `tools/luacheck.py` | Lua syntax, via a real Lua VM |
| `tests/test_assets.py` | sprites, items, meshes, textures, icons, the phaser's borrowed vanilla references, and every translation key |
| `tests/test_stock.py` | items that cannot be created at all; loot that does not spread across its list; containers that do not reach `C.FillFraction` |
| `tests/test_multiplayer.py` | the real code as single player and as a server with two clients: cabin build and stock reaching every client, ownership and crew, transporter charges, landing round trips, ghosts, shields pushing only local zombies, a client editing the world or ship state, commands without handlers, missing file guards, role-gated setters, any logged `WARN` |
| `tests/test_helm.py` | helm console throws, draws out of bounds, clipped labels, dead controls, controller-unreachable buttons |
| `tests/test_layout.py` | fittings outside the hull, on the pad or stacked; containers not flagged as containers; loot lists that do not exist; the Lua drifting from the `.tbx`; multi-tile offsets vs `SpriteGridPos`; the footprint against the mesh |

`test_stock.py` stubs the engine **the way it really behaves** — `instanceItem`
present, `InventoryItemFactory` nil — and its first assertion is simply that an
item can be created. Against the old code that assertion prints `0 items` and
fails. Keep it first: with item creation broken, every other check in the file
still passes on an empty container, which is exactly how this reached the game
twice.

These have caught more real bugs than the in-game test has. Extend them in
preference to adding in-game checks — but note what they cannot do: they run a
Lua VM with *stubs*, so they prove the mod's own logic and never that an engine
call is real. Only the game does that, which is what the log lines below are
for.

### In game

Load a **fresh** world. Nothing runs by itself any more: the old in-game
self-test beamed the character across the map and was removed with flight.
The debug console functions ask the server, which allows them in single player
or for an admin, and write their report to the server's log (`console.txt` in
single player, `server-console.txt` on a server).

| Console function | Does |
|---|---|
| `TREK_Stock()` | One line per container: items held and how full. **The first thing to run when loot looks wrong.** |
| `TREK_Galley()` | Put one of each galley dish in your inventory |
| `TREK_Water()` | Top the fixtures up and log capacity, amount and `hasWater` for each |
| `TREK_Shields()` | Report the shields; `TREK_Shields(false)` / `(true)` asks to set them |
| `TREK_Rebuild()` | Tear down and regenerate the cabin, restocked. Stand aboard. **Destroys contents.** |
| `TREK_Beam()` | Beam up if outside, down if aboard |
| `TREK_Room()` | Report whether the ship could land here and what is in the way (this client's view) |
| `TREK_Phaser()` | Report phasers found on you and recharge them |
| `TREK_Ghosts()` | Sweep hulls waiting to be cleared, and strays near you |
| `TREK_Charges()` | Log whether beams are rationed on this server and your charges |

### On a dedicated server

A local dedicated server is installed for testing; it is a **test harness
only** -- nothing in the mod may depend on it.

```sh
PZ="$USERPROFILE/Zomboid/PZ-Worlds.ps1"
powershell -File "$PZ" list                               # worlds
powershell -File "$PZ" new trektest -Template servertest  # accounts copied, no mods
powershell -File "$PZ" mods trektest enable TrekShuttleDev
# and in Zomboid/Server/trektest.ini:  Map=TrekShuttle;Muldraugh, KY
powershell -File "$PZ" start trektest                     # join at 127.0.0.1:16261
powershell -File "$PZ" stop
```

Deploy first (`tools/deploy_windows.py` installs `TrekShuttleDev` where the
server reads it). A fresh world takes 3-6 minutes to generate. The in-game Host
button has never worked on this PC; test co-op when another machine can.

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

Version **1.3.0**, build revision **12**.

**1.3.0 is the multiplayer rewrite** (MULTIPLAYER.md, migration steps 1-9):
server-owned ship and cabin, request protocol, transporter charges, shields per
client, owner-and-crew access, the shuttle as a four-seat vehicle, and flight.

**Seen working in game** (2026-09-17): the BuildingEd interior and its nineteen
stocked containers, the helm console, the galley food, the whole single-player
path through the new request protocol — beam up, cabin, helm, take her down,
hatch, beam down — and **piloting**: take off, climb, dive, fly over buildings,
set her down, with the crew going aft to the cabin and back in the air. See
`PILOTING.md`.

**The 2026-09-18 session** carried the drinks and the bat'leth in for the first
time and cost five bugs, all fixed and all now covered: `ClearBlue` was not a
registered colour and **no world would load at all**; a weapon model in the
mod's own module drew nothing; beaming up never left the vehicle seat, so
vanilla's inventory walked a null vehicle every frame — 829 stack traces and an
unresponsive game; and the bat'leth was twice its proper size with an icon that
bled into the next hotbar slot.

**Seen working in game** (2026-09-20): the **bat'leth** at its corrected size
(bounding box 0.531 → 0.369 across) with a 32×32 icon that stays in its own
hotbar slot, and the **four galley drinks**. The drinks were in the *oven* —
the entry hung `loot = "drinks"` on the lower half of a two-tile stove while
the comment beside it said "cabinet" — and have moved to the counter at 5,0,
where the deck plan can also show them. Revision 12.

**Not yet seen in game**, in the order worth checking:

1. **The dedicated server**: the interior cell loads there, the server-built
   cabin reaches the client with its stock, water fills with the mains off.
2. **Two players**: one cabin, loot taken by one gone for the other, crew
   access, charges — and a shuttle in the air seen from the other machine,
   which is the last unproven thing about flight.
3. **The phaser firing** and staying charged on a server.

**The pattern worth carrying forward.** Six separate bugs in this mod have
had the same shape: a plausible engine call that fails silently, leaving a
thing that is present, drawn, and inert — an unopenable locker, a container
handed items that were never created, a tap topped up through an API it does
not have, a menu hook that never ran, a floor removed without its shadow, a
weapon model declared one module away from where the engine looks. Static
checks caught none of them, because the mod's logic was correct every time. What caught them was **reading the result back and logging
it**: `B.stockReport()` turned three sessions of guessing into one grep. When
you add something to the cabin, add the line that proves it arrived.

Known limits are listed at the bottom of `README.md`.

---

## Layout

```
design/buildinged/TrekShuttle_Interior.tbx                     the interior, in the map editor
TrekShuttle/42/media/sandbox-options.txt                       server-owner settings
TrekShuttle/42/media/lua/shared/TREK/TREK_Config.lua           all constants — start here
TrekShuttle/42/media/lua/shared/TREK/TREK_Util.lua             safe wrappers, state schema, geometry, stocking
TrekShuttle/42/media/lua/shared/TREK/TREK_Net.lua              client -> server commands, replies
TrekShuttle/42/media/lua/shared/TREK/TREK_Ship.lua             publishing the ship state, access rules
TrekShuttle/42/media/lua/shared/TREK/TREK_World.lua            read-only landing and standing queries
TrekShuttle/42/media/lua/shared/TREK/TREK_InteriorLayout.lua   the interior as data + loot
TrekShuttle/42/media/lua/server/TREK/TREK_Build.lua            cabin construction, stock, water
TrekShuttle/42/media/lua/server/TREK/TREK_Server.lua           command handlers, hull, ghosts, charges
TrekShuttle/42/media/lua/client/TREK/TREK_Core.lua             asking to move, arrival, hatch, shields, lights
TrekShuttle/42/media/lua/client/TREK/TREK_Transport.lua        the transporter
TrekShuttle/42/media/lua/client/TREK/TREK_Sky.lua              the invisible floor the ship flies on
TrekShuttle/42/media/lua/client/TREK/TREK_Flight.lua           taking her up, changing level, setting down
TrekShuttle/42/media/lua/client/TREK/TREK_Helm.lua             the LCARS helm console
TrekShuttle/42/media/lua/client/TREK/TREK_Travel.lua           courses, map picking, landing search
TrekShuttle/42/media/lua/client/TREK/TREK_Phaser.lua           keeping phasers charged
TrekShuttle/42/media/lua/client/TREK/TREK_Menu.lua             right-click menus, crew
tests/pz_sim.lua, tests/test_multiplayer.py                    the simulated engine and network
```

---

## Changing the interior or what is in it

The two common jobs, end to end.

### Moving or adding furniture

1. Edit `design/buildinged/TrekShuttle_Interior.tbx` in BuildingEd.
2. `python tools/import_tbx_layout.py` — prints every furniture tile it
   expands and, separately, **every one the tileset says is a container**.
3. Carry the changes into `L.tiles` in `TREK_InteriorLayout.lua`. Geometry
   (`x`, `y`, `sprite`) comes from the `.tbx`; `tag`, `container` and `loot`
   are yours, which is why the file is not simply regenerated over the top.
4. Every container needs **`container = true` and a `loot` list**, or it is
   placed as scenery and can never be opened.
5. Bump `C.BuildRev`.
6. `python tests/test_layout.py` — it fails if the Lua and the `.tbx` disagree
   about containers, and prints the deck plan. Look at it.

### Changing what is in a container

Edit the `C.Loot` list in `TREK_Config.lua`, or point the entry's `loot` at a
different one. Then:

```sh
python tests/test_assets.py     # every id exists in build 42
python tests/test_stock.py      # the lists spread, and fill to target
```

`test_assets.py` checks ids against `tools/_catalog/items.json`. It does **not**
check for items flagged `Obsolete` — those exist in the scripts and still
return nil from `instanceItem`, which looks exactly like an empty container. If
a new id misbehaves, grep the game's scripts for its block and look.

Amounts are not set per container: everything fills to `C.FillFraction` of its
own capacity. To make one container fuller than the rest, give its entry a
`fill` (fraction) or `cap` (item count) override.

**Bump `C.BuildRev` either way**, so the cabin is revisited -- but remember
*Never restock an existing container*: new loot reaches new worlds, and
`TREK_Galley()` or `TREK_Rebuild()` for testing.

---

Almost every change is `TREK_Config.lua`, or the `.tbx` plus
`TREK_InteriorLayout.lua`.
