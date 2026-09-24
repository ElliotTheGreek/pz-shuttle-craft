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

There are three tools, and they answer three different questions. Reaching for
the wrong one is how two designs here were nearly got wrong:

| Tool | Answers |
|---|---|
| `tools/pzapi.py` | does this method exist, and is it public? |
| `tools/javarefs.py` | what does it touch? — **bytecode order, no branches** |
| `tools/javadis.py` | **under what condition?** |

`javarefs` lists references as they appear, which is not control flow: it shows
`BaseVehicle.update()` calling `setZ(0)` and `setZ(level)` and cannot tell you
the first is unconditional and the second sits behind a floor check — the fact
the whole flight design rests on. `javadis.py` disassembles one method with
branch targets resolved, which is what settled that, and what showed that a
trap's fire roll is taken **per square** and that `triggerExplosion()` skips
any explosion mode whose range is zero -- the two facts the photon torpedo's
whole visible half turned on (`PHOTON_TORPEDOS.md`).

**Read the list as "may", and the disassembly as "does".**

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

And **read the path of the call site you find**, which is the one refinement
this rule has needed. `getAllItems()` -- the whole of the replicator's
catalogue -- has an obvious call site in `ISItemsListViewer.lua`, and that file
is in `client/ISUI/**AdminPanel**/`. A call site under `AdminPanel/` or
`DebugUIs/` proves a method works *for an admin, in a debug build*, which is
the `setGodMod` shape one level up: exactly the thing this section exists to
catch. The two that made `getAllItems()` safe to build on were
`shared/Foraging/forageSystem.lua` and `client/ISUI/ISLiteratureUI.lua`.

```sh
PZ="/c/Program Files (x86)/Steam/steamapps/common/ProjectZomboid/media/lua"
grep -rn "getAllItems()" "$PZ"      # and then look at the directories
```

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

### A vanilla call site proves reachability, never correctness

**New in this mod, and it is the sharpest edge of the rule above.** Grepping
vanilla Lua answers "may I call this". It does not answer "is this the call I
want", and the two are easy to run together when the grep comes back with
eight hits.

`BodyPart.SetBitten(false)` is the obvious way to cure a bite. It is public,
it reads exactly like what it says, and **vanilla's own admin health cheat
calls it that way in two places** -- `ClientCommands.lua:490` and
`ISHealthPanel.lua:222`. Every test this repository knows how to write would
have passed. The disassembly:

```
SetBitten(Z)      2  putfield  BodyPart.bittenZ      <-- the argument
                  6  ifeq -> 102                     <-- only the bleed block
                120  putfield  BodyPart.isInfectedZ = 1
                163  invokevirtual BodyPart.generateBleeding()
```

The guard ends at bci 102 and **everything after it runs whatever you passed**.
So `SetBitten(false)` clears the bite, infects the limb and starts it
bleeding. A player who paid a dilithium crystal and slept twelve game hours
would have woken up infected, on an arm that was now bleeding, with the mod
reporting a successful cure and the log saying nothing at all.

The two-argument form puts the whole block behind its first argument
(`33 iload_1; ifeq -> 105`) and is safe. So is `RestoreToFullHealth()`, which
writes thirty-seven fields by direct putfield and calls nothing.

Three things follow:

- **A vanilla call site is evidence about the method's reachability and
  nothing else.** It says the global resolves and the engine accepts the
  arguments. It says nothing about whether the author of that call site wanted
  what you want -- and an *admin cheat* wants the limb bitten-and-infected,
  because it is about to restore the whole body anyway.
- **An overload count is a warning.** Two signatures for one name usually
  means one of them grew a flag, and the flag usually guards something.
- The same shape is in this file twice already -- `setGodMod` (public, silently
  refuses) and `getAllItems()` (real, but found under `AdminPanel/`). This is
  the third face of it: **real, reachable, called by vanilla, and wrong.**

**And design out the permission instead of fighting it.** Hands-on flight
tried to keep the pilot safe with those setters, then by holding the body in
mid-air; both failed in game, and flying a body at 90 tiles a second would be
kicked by the speed anti-cheat on any server. It was removed, and came back as
something the engine cannot argue with: the ship is a **vehicle**, a seat with
no door cannot be bitten, vehicles may travel fast, and no character is moved
at all. See `PILOTING.md`.

The same reasoning applies to *which* API a given object actually uses — see
*Two APIs for water* below.

### A guard is only as good as the goal it was written from

**New in this mod, and it is the only bug here that every static check
defended.** The photon torpedo killed what was in its blast and nothing was
ever seen to happen — no flash, no fire, no smoke. The cause was
`C.TorpedoFireChance = 0`, and three things were holding it there:

1. the constant;
2. a long comment above it explaining why zero was correct, ending "raise it
   and the mod sets Muldraugh alight";
3. a test that failed if it was ever raised, labelled *"THE one that matters"*.

Every one of those was **accurate about the engine**. `IsoTrap` really does
gate `Burn()` and `IsoFireManager.StartFire` on that roll; raising it really
does set fire to things. What they were wrong about was the *goal*: they came
from reading one line of `ROADMAP.md` — "an explosion that does not set the
street on fire" — as *no fire at all*, when it meant *fire as an intended
weapon effect rather than an accident*.

And because in this engine **the visible part of an explosion is the fire and
the smoke** — there is no separate explosion effect — suppressing the fire
suppressed the entire weapon except the damage.

So the test passed, the comment justified it, and the feature was broken in
exactly the way the user could see and the repository could not.

- **A test encodes an expectation, not a fact.** When a feature is reported
  broken, the tests covering it are suspects, not witnesses. Read what they
  assert and ask where that expectation came from.
- **An emphatic comment is the strongest possible signal to check.** "Must
  stay 0" is a claim about intent, and intent is the thing a source file is
  worst at recording.
- **Say which line of the spec a guard came from.** Had the comment cited the
  roadmap wording it was derived from, the misreading would have been visible
  the first time anyone looked.

### `setHaveElectricity` does not set anything, and `haveElectricity` means "a generator"

**New in this mod, and it was a no-op from the day it was written.** The cabin
had a `B.powerCabin()` that called `sq:setHaveElectricity(true)` on every
square, at build time and again every game minute. It never did a thing, and
the only symptom was a television nobody could switch on:

- **`IsoGridSquare.setHaveElectricity(boolean)` sets no field.** Its bytecode
  walks `getObjects()` and touches `IsoLightSwitch`es. A cabin with no light
  switches is a cabin where that call is a loop over nothing.
- **`IsoGridSquare.haveElectricity()` is not a flag either.** It returns
  `chunk.isGeneratorPoweringSquare(x, y, z)` -- true only when a real
  `IsoGenerator` is running in that chunk.
- **`IsoGridSquare.hasGridPower()`** is `!isNoPower() && doesPowerGridExist()`:
  the town mains, which shut off a few weeks into any world.

So an appliance somewhere off the map can be mains-powered in exactly two
ways, a generator or the town grid, and both are wrong for a spaceship.

What works is one branch further in. `DeviceData.canBePoweredHere()` opens
with `if (isBatteryPowered) return true` **before it looks at the square at
all**, and that is what both `setIsTurnedOn` and the per-minute `update()`
consult. A device with `isBatteryPowered` set and its power kept above zero
switches on anywhere, needs no square, no room and no generator, and stays on.
`TREK_Power.lua` is that, and its header has the bytecode.

Three things the disassembly settled that guessing would not have:

- **A battery-powered device switches itself off at zero.** `update()` drains
  `useDelta` per game minute while it is on, and the stay-on test is
  `isBatteryPowered && power > 0` *before* it falls through to
  `canBePoweredHere()`. So "battery powered" is not "powered for ever" -- it
  needs topping up, like the phaser's charge.
- **The top-up has to run in every process.** `DeviceData.update` drains the
  value wherever it runs, and on a client it transmits the drop itself. A
  server-only top-up leaves every client switching the television off by
  itself after a couple of game hours. `TREK_Power.lua` is therefore
  **shared**, and the local write is in the same category as the lights and
  the shields -- a value the engine recomputes per process, not ship state.
- **Leave `hasBattery` false.** The engine never reads it; `RWMPower.lua`
  does, and offers *Remove Battery* when it is true -- which would hand the
  player a free `Base.Battery` every time they opened the panel.

`TREK_Power()` from the console reports each fitting's cell and whether it has
device data at all, which is the line that tells "the television is off" from
"the television is scenery".

### A sprite is not the object the engine builds from it

**New in this mod, and it hid a whole appliance in plain sight for three
versions.** `TREK_Build.place()` makes every fitting with
`IsoObject.new(sq, sprite, tag)`. Hand it a television's sprite and you get an
`IsoObject` wearing a television's picture: no device data, no channel, no
volume, no tape slot, nothing to right-click. The cabin's viewscreen was that
from the day it was added, and nobody noticed because nobody ever tried to
turn it on.

The engine decides the *class* from what built the object, not from the
sprite. Vanilla's own route is `ISMoveableSpriteProps.lua:2136`:

```lua
local obj = IsoTelevision.new(getCell(), sq, getSprite(sprite))
obj:setDeviceData(obj:cloneDeviceDataFromItem("Base.TvWideScreen"))
```

Two things worth carrying:

- **`IsoWaveSignal.cloneDeviceDataFromItem(String)` is the short way**, and the
  disassembly is why it is safe: it caches per id, returns a *clone*, and
  reaches `InventoryItemFactory.CreateItem` **in Java** -- which works even
  though the Lua global of that name is null (*The jar is not the API*). It has
  no vanilla Lua call site, so the build tries it, falls back to
  `instanceItem(id):getDeviceData()`, and then **reads `getDeviceData()` back
  and logs it**. A television with nil device data looks exactly like a working
  one.
- **The same applies to a lot of sprites.** Anything whose tile properties name
  an `IsoType` -- `IsoStove`, `IsoTelevision`, `IsoLightSwitch`, `IsoDoor` --
  is a different Java class in a map-loaded world and a plain `IsoObject` at
  runtime. `createContainersFromSpriteProperties` is the same lesson one level
  down and has been in this file since the first empty locker.

And the inverse, which decided where the EMH's button went: **do not place a
sprite whose properties would make the engine build something else.** Every
`lighting_indoor_01` switch carries the `lightswitch` property, which is what
the cell loader reads when it builds an `IsoLightSwitch`. A mod button that
turns into a real light switch on the next world load is a bug that only
appears in somebody else's save.

### Half the tileset does not block its square

**New in this mod, and it is what made a twenty-four square cabin possible.**
A fitting is an obstacle only if its tile carries `solid` or `solidtrans`. A
great many do not:

| Sprite | What it is | Blocks? |
|---|---|---|
| `security_01_4/5` | wall-mounted monitor bank | no |
| `industry_01_4/5/14/15` | wall-mounted panel, the hull's own wall set | no |
| `furniture_shelving_01_28..31` | metal wall shelves, **capacity 30** | no |
| `fixtures_sinks_01_*` | a sink, which rides on a counter | no |
| `lighting_indoor_01_32` | a deckhead lamp | no |
| `location_entertainment_theatre_01_3` | a chair -- `collideN` only | **north edge only** |
| `furniture_storage_02_*`, counters, fridges, ovens | lockers and appliances | yes |

Two consequences that are easy to get backwards:

- **A wall object costs no floor.** The whole bow bulkhead of this ship is a
  four-panel monitor wall and all four squares are still deck.
- **A chair with `collideN`/`HoppableN` blocks one edge.** You can walk along a
  row of them east-west and step onto one from the south; a two-tile bench seat
  (plain `solidtrans`) would wall the row off. The bow row of the cabin works
  only because of this, so read the properties before swapping a seat.

`tests/test_layout.py` reads this out of `tools/_catalog/tiles.json` now rather
than assuming every fitting is an obstacle, which is what had it refusing a
layout that was actually fine.

### A wall keeps a player in only where the engine thinks there is a building

**New in this mod, and it killed people.** Build 42 lets a player climb over a
**wall**, not merely a fence, and the cabin is exactly the shape that permits
it: climb out of the hull, walk one more square, and fall for ever.

`IsoPlayer.canClimbOverWall(dir)` is the gate, and every early return in it is
about a *building*:

```
 30  getfield  IsoGridSquare.haveRoof      ifeq -> 38   ; a roof: refused
 42  invokevirtual  IsoGridSquare.getBuilding()         ; in a building: refused
112  getfield  IsoGridSquare.haveRoof                   ; and the same two
137  invokevirtual  IsoGridSquare.getBuilding()         ; for the far side
248  IsoFlagType.CantClimb                              ; or the flag
```

Every wall of every house on the map is refused by the first two. **The cabin
is raised at runtime in a cell with no map behind it**, so it has no roof, no
`IsoRoom` and no `IsoBuilding` — to the engine it is four walls standing in a
field, and a field is the one place climbing a wall is meant to work. Nothing
in the mod was wrong; the cabin simply is not a building, and *every* engine
behaviour that keys on one has to be read in that light.

And `isSafeToClimbOver` only asks whether the destination has a floor, which
the ring outside the hull does: `buildFloor` lays deck under every square a
wall stands on, because a wall on a midair square behaves badly. So the climb
looked safe to the engine, landed on deck, and the void was one square further
on.

- **The fix is the engine's own switch.** `IsoPlayer.ignoreAutoVault` is read
  as the *first instruction* of both routes in — `doContextClimbOverWall` and
  `doContextHopOverFence` — before either offers the contextual action, and
  `climbOverWall` is only ever reached from an action one of them added.
  Vanilla's tutorial sets it the same way (`client/Tutorial/Steps.lua:214`).
  `TREK_Core.holdVault` sets it while a character is aboard **and clears it
  when they leave**: a flag left on would follow that character for the life
  of the save, and a crewman who could no longer climb a fence is a worse bug
  than the one it fixes.
- **`IsoFlagType.CantClimb` was the obvious answer and is not durable.**
  `IsoGridSquare.has(IsoFlagType)` reads the square's `PropertyContainer`, and
  `RecalcProperties()` opens with `properties.Clear()` and rebuilds it from
  the objects' *sprite* properties. Anything set by hand is gone the next time
  an object is added or the chunk reloads, in every process, and it would be
  gone for exactly the one frame that mattered.
- **"Is there a floor under me" is not "am I aboard".** The rescue in
  `checkAboard` had always asked the first, and the ring the walls stand on
  answers yes. It asks `U.isAboard` now — the cabin's own shape — because
  nothing that carries anybody aboard ever puts them outside `C.inShape`.
- **A rescue on a timer has to beat a fall.** That check ran on every tenth
  player update, which is nine frames of falling; it runs on every one now,
  and puts the player back with `Core.hold` rather than `U.teleport`, because
  the engine carries its own fall state through a move and a falling player
  simply falls again from the pad. That is what "an infinite fall" was.

The general shape, and it is worth more than the bug: **a runtime-generated
interior is not a building, and the engine's own idea of indoors is what a
great many of its rules key on.** Roofs, rooms, buildings, `isOutside`,
climbing, rain, temperature and the camera's cutaway all read it. Before
relying on any of them, ask what `getBuilding()` answers out here — it is
always `null`.

### `U.clearSquare` keeps two things on purpose, and a migration has to name them

**New in this mod.** `clearSurroundings` strips the ring around the cabin
"down to nothing", which sounds total and is not. `U.clearSquare` deliberately
preserves:

1. **anything the mod tagged** -- so a rebuild does not eat its own furniture;
2. **anything lying on the ground** (`IsoWorldInventoryObject`) -- so it does
   not eat the player's dropped things.

Both are right, and both mean that **shrinking the cabin cannot be left to the
clearing passes.** When the interior went from 6x9 to 4x6, every locker,
fridge and bunk outside the new hull would have been left standing, openable,
in the black void for the life of the save -- and the helm console prop, a
world item, would have survived even inside it. `B.refitCabin` names both, and
the general rule is: *a pass that keeps things by policy cannot also be the
pass that removes them when the policy changes.*

Three details of that migration worth reusing:

- **The chunk is the gate, not the square.** A nil square in a *loaded* chunk
  really is nothing there; only an unloaded chunk means "ask again later". Get
  that backwards and the sweep never marks itself done and re-walks the extent
  on every build for the rest of the save.
- **Write the old extent down.** `C.LegacyCabin = { w = 5, l = 8 }` exists
  because nothing that walks the new shape ever visits those squares, and a
  number in a comment is not a thing code can iterate.
- **Hand the contents back.** A container that is about to stop existing
  spills onto the transporter pad, and it moves the **live `InventoryItem`**,
  not its id: recreating from the full type resets a hypospray's doses and a
  magazine's rounds, which is the quiet half of losing it.
  `AddWorldInventoryItem(InventoryItem, f, f, f)` is the overload for that.

### State that is transmitted whole cannot hold a list that grows

**New in this mod.** `Ship.commit()` calls `ModData.transmit(C.StateKey)`,
which sends the *entire* ship table to every client. That is fine for what was
in it -- a position, a few flags, forty bookmarks -- and it is fine because
those change rarely.

Except they do not. `S.serviceVehicle` commits whenever the shuttle has moved
a square, which while anybody is flying her is about once a second. Every
commit is the whole table.

The replicator's pattern set is a list of item ids that grows for the life of
the save, and `REPLICATOR.md` originally put it in the ship state with a note
to "measure it before shipping". The measurement is not needed: two thousand
patterns times once a second is the answer. It has its own mod data key
(`C.PatternKey`), the same request-and-receive handshake `TREK_Ship` uses, and
it is transmitted only when a pattern is actually learned. The *reserve* --
one number -- stayed in the ship state, where it costs nothing.

The general shape: **before putting something in a table that is published on
every change, ask how big it gets and how often that table is published.** The
two questions have different answers and both matter.

### The simulation has to be as unkind as the engine

**New in this mod, and it cost three separate holes in one afternoon.**
`tests/pz_sim.lua` is the only thing standing between a multiplayer bug and a
second machine, and every place it is *gentler* than the real engine is a
place a test passes and the game does not. Three were found in one pass, all
by writing a test that should have been hard to satisfy and watching it sail
through:

1. **A container that never refuses.** `ItemContainer.AddItem` drops what it is
   handed once the contents reach capacity, silently -- which is the whole
   reason `U.stockEach` reads the container back. The stub accepted everything,
   so "the tray is full" could not be tested at all.
2. **Panels with no children.** `instantiate()` was a no-op, but the engine's
   creates the Java `UIElement`, whose constructor calls back into Lua's
   `createChildren`. Every panel opened in the simulation had no buttons in it,
   so a test could only reach a feature by calling its handlers -- and a button
   wired to nothing would have passed.
3. **Buttons that dropped their handler.** The stub's `new` took only a
   rectangle, so `title`, `target` and `onclick` went on the floor.

Two more since, from the dilithium work, and both are the same shape:

4. **A fitting the simulation does not think is a container.** A placed object
   gets its container from a list of substrings in its sprite name, and the
   dilithium chamber's `location_business_machinery_01_33` matched none of
   them. The cabinet was placed and never stocked, so eight checks failed on a
   power system that was working perfectly. **Any new fitting that holds
   something has to be added to that list**, or it is scenery in every test.
5. **A catalogue that had never heard of the item.** The check that the
   replicator refuses to make a dilithium crystal passed because the
   simulation's item list did not contain one. Deleting the blocklist entry
   changed nothing at all. The three items the replicator must refuse are
   declared in `pz_sim.lua` now, for that reason alone.

Two more again, from the warp core:

6. **A seated character was still on the tarmac.** `PlayerMT:getZ()` answered
   the last z anybody had set on them, while the engine moves a passenger with
   the vehicle every tick. A pilot at cruise reported ground level, which made
   the cockpit indistinguishable from the runway -- and the tricorder's whole
   reason for reading downwards in flight is that the two are three levels
   apart.
7. **Only half of the inventory sync existed.** `sendAddItemToContainer` was
   stubbed and `sendRemoveItemFromContainer` was not, so the first thing the
   mod ever took *out* of a player's inventory on the server threw. Both
   directions are there now, and both reach only the player whose pockets they
   are.

And one more, the most expensive of the set, because it hid a bug that
shipped:

8. **A vehicle whose physics this machine always owned.**
   `isLocalPhysicSim()` was stubbed as `SIM_ROLE ~= "server"` -- true in
   single player. The engine answers **false** there, for ever, and
   `takeoffGranted` had grown a guard on it, so a real single-player game
   could not take off at all while every test passed. The stub models the
   engine's own rule now: false in single player, and on a client true only
   for the machine whose player is driving. See *Single player is neither a
   client nor a server* below.

And one more, from the first two-player flight, which is the same fault as 6
one level further in:

9. **A vehicle whose angles were three stored numbers.** `getAngleX/Y/Z` do not
   read fields in the engine: they decompose the rotation quaternion with
   JOML's `getEulerAnglesXYZ`, and the X of that is 180 for a *level* ship
   turned more than a quarter turn from the identity. The stub handed back
   whatever `setAngles` last stored, so the artefact could not exist here -- and
   its `flipUpright` kept the heading, where the engine's resets the whole
   rotation to the identity. The mod's levelling pass was therefore hauling the
   ship back to her spawn heading ten times a second in game, and the entire
   flight suite was green. The stub keeps a real quaternion now.

And a tenth, found in play on 2026-09-24:

10. **A seat test that answered nil.** `BaseVehicle.getSeat(character)`
   returns **-1** for somebody not in the vehicle (bci 27, `iconst_m1`); the
   stub returned nil. `crewAboard` asked `getSeat(p) ~= nil`, so in the game
   every living player near a hovering shuttle counted as her crew -- a crew
   who beamed down beside her were told "Not while the shuttle is in the
   air" when they called her down -- and here nobody ever did.
   `hover_call_down()` reproduces the exact message against the old line.

All ten are fixed, and the rule they share is worth more than any of them:
**when a test is easy to satisfy, suspect the simulation before believing the
code.** `MULTIPLAYER.md` says the same thing about vehicle gravity, the
floor-gated height and the radial menu's one-frame delay, each of which let a
real bug through first.

### A check against an empty set is not a passing check

**New in this mod.** `tests/test_assets.py` reads the twelve vanilla loot
tables dilithium is seeded into and looks each one up in the installed
`ProceduralDistributions.lua`. The first run reported all twelve missing --
and every one of them was there. The pattern reading vanilla's file expected
four spaces of indentation and vanilla uses tabs, so the set it compared
against was empty, and *everything* is missing from an empty set.

An empty-set comparison fails loudly, which is lucky; the same mistake on the
other side of a check passes silently and proves nothing for as long as the
file lives. **Both sides of a lookup check need a floor**: this one fails now
if fewer than five ids come out of the mod's file or fewer than a hundred
tables out of vanilla's, and either message says the pattern has stopped
matching rather than blaming the data.

The general form, which applies to every filter, catalogue and id check in
here: *if a check can pass because it had nothing to check, it is not a
check.*

### A branch a mutation cannot break may be unreachable

**New in this mod.** The replicator shipped with two refusals: "not enough in
the reserve" when spare crystals were aboard, and "no dilithium" when they
were not. Deleting the first one broke no test. The first instinct was to go
and write a test for it -- and there was no test to write, because **the
branch could not be reached**: a fresh crystal is five thousand units, the
dearest thing in the game costs fifteen hundred, so a swap always covers the
cost and the "not enough" case never happens.

So when a mutation changes nothing, there are two possibilities and they want
opposite fixes:

- the tests do not cover it -- **write the test**;
- nothing can reach it -- **delete the code**, and say why in the file that
  replaces it.

Telling them apart takes one honest look at the numbers, and it is worth doing
every time: the unreachable branch had a translation string, a client handler
and a matching rule in the panel for greying its own button. That rule was
wrong in a way a player would have seen -- it greyed a button on a low reserve
even though the ship would have loaded a crystal and made the thing.

### A test harness must record the distinctions the code makes

**New in this mod.** The tricorder plots a lifesign as a small filled square
and a dilithium trace as a ring with a bright middle -- deliberately different
shapes, because a fourth shade of dot among three is one more thing to squint
at. The UI harness recorded `drawRect` and `drawRectBorder` as the same kind
of draw, so no test could see the difference: a plot that drew *no* crystal
traces at all passed, and so did one that drew them against the wrong radius.

The harness records them apart now, and the checks are about position rather
than presence -- a trace at the edge of the mineral radius has to land on the
edge of the plot. **If the code distinguishes two things, the harness has to,
or every test about the difference is decoration.**

### A prop that nothing opens is worse than no prop

**New in this mod.** The cabin carried a `TrekHelmConsole`: a generated static
model, 70 weight, standing on the deck. The helm panel opens from the aboard
menu -- right-click anywhere aboard, *Shuttlecraft*, *Helm* -- and never from
that object, so the model was scenery that looked like a control. In a
fifty-four square cabin it read as furniture. In twenty-four the author's
description was "a big blocky thing that seems to have no function", which is
exactly what it was.

The mod's own rule about dead placement code (*Dead placement code is worse
than none*) has a counterpart in the world: **a model that looks interactive
and is not teaches the player the wrong thing about your ship.** Either wire it
up or take it out.

### A fixture that leans on another fixture is not a fixture yet

**New in this mod, and the author had to say it twice.** The replicator was
built as a model hanging over one of the galley's steel counters: the counter
provided the container that replicated items appeared in, and the model
provided the look. Two objects on one square pretending to be one machine.

Everything wrong with it followed from that. The model had to float, because a
floor-standing unit would have been drawn through the counter -- and a
floating model cannot be right-clicked (below). The output went into a piece
of furniture indistinguishable from the two identical counters beside it. And
the layout carried a container whose real job was to be somebody else's
inventory.

Standing it on its own square removed all of it, including code: no tray to
find, no tray to count, no "the tray is full" path. **If a new fixture needs
an existing one underneath it to work, the design is not finished** -- and the
tell is that the new thing cannot be placed where it belongs without the old
one showing through.

### A right-click lands on the floor, not on the picture

**New in this mod, and it made a finished feature unusable while looking
perfect.** The replicator's alcove is a world model authored to hang above the
galley counter, and it drew exactly as intended: lit recess, LCARS surround,
sitting over the bench. It could not be right-clicked at all.

`OnPreFillWorldObjectContextMenu` hands you the cursor's screen position, and
the square is resolved with `screenToIsoX/Y(playerIndex, x, y, z)` -- which
converts a *screen point to a square on the floor plane at that z*. The model's
pixels are a metre and a half above that plane, so the square the engine names
is the one a tile or two north-west of the one the model belongs to. A menu
keyed to the model's own square is therefore never offered when the player
aims at the model.

This is not special to a floating model: it is true of every tall object in
the game, which is why you interact with a fridge by clicking its base. What
made it fatal here is that the alcove has *no* base -- there is nothing of it
drawn on its own square to click.

Two things follow:

- **Give a click a margin when the thing it is aimed at is tall.**
  `BERTH_MARGIN` is one square, which covers the drawn height and still leaves
  the transporter pad two squares away offering nothing. The test asserts both
  ends, and both mutations are caught.
- **Or put the object on the floor**, where the gesture and the geometry agree.

The cheap tell from outside the game: the feature works, the log says the
fixture was placed, and there is no error anywhere -- because nothing is
wrong. The menu is simply being asked about a different square.

### A dropped world model picks its own angle

**New in this mod.** Both of the ship's machines are placed with
`sq:AddWorldInventoryItem(...)`, and both stood at a random yaw until somebody
looked at a screenshot. `IsoWorldInventoryObject`'s constructor is the reason,
and the bytecode says it plainly:

```
worldXRotation = 0
worldYRotation = 0
if (worldZRotation < 0) worldZRotation = Rand.Next(0, 360)
```

A fresh item's `worldZRotation` is negative -- nobody has set it -- so every
dropped thing lands at a random angle. That is right for a hammer on the floor
and wrong for a machine bolted to a bulkhead.

The fix is three setters after the placement, and two things make it stick:
the rotations are **saved and loaded with the item**, so setting them on the
server persists and reaches clients with the item itself, and the build pass
straightens whatever is already standing there, which is the only thing that
will ever touch a machine in an existing save.

`tests/pz_sim.lua` does the same thing with a fixed angle now -- the
simulation has to be as unkind as the engine, not as unpredictable.

### A check that runs after a self-healing pass checks the healing, not the thing

**New in this mod, and it happened twice in one afternoon.** Both machines are
straightened on placement *and* again by every later build pass, which is what
brings a crooked one in an existing save back square. The test asked for the
angle after a block that had already rebuilt the cabin twice -- so deleting
the straightening at placement changed nothing, and the mutation that should
have caught it sailed through. The warp core's version of the same check, a
hundred lines later, had exactly the same hole.

Both now ask **before anything rebuilds**, and the repair path is a separate
check that deliberately makes a mess first.

The general shape: anything that is fixed up on every pass -- a migration, a
restock, a straighten, a re-seed -- will cover for the code that should have
got it right the first time. Order the test so the first observation happens
before the second chance.

### A string that gets upper-cased has to be ASCII

**New in this mod, and cheap to learn twice.** A panel title drawn as
`string.upper(getText(...))` went through a Lua `upper` that works a byte at a
time: an em dash came out as mangled bytes, and the UI harness died decoding
them. Punctuation in prose is fine; punctuation in a string the code
upper-cases is not.

### A convenience method is a bundle of writes somebody else chose

**New in this mod, and it was one line from shipping.** `BodyPart
.RestoreToFullHealth()` is the obvious way to mend a limb, it is public, it
has eight vanilla Lua call sites, and it does considerably more than mend it:

```
  1  ldc_w  100.0     putfield BodyPart.health
 37  fconst_0         putfield BodyPart.biteTime
 42  iconst_0         putfield BodyPart.bitten        <-- here
 92  iconst_0         putfield BodyPart.infectedWound
```

The hypospray is specifically decided **not** to cure a bite -- that cure is
the EMH's and is the only reason the EMH is worth building -- so the tidy
version of that feature quietly hands a pocket item the one thing the game is
built around, makes the next item on the roadmap pointless, and **reports
nothing at all**. It is not a bug anybody would see. It is an item that is
better than intended.

So `TREK_Medical.lua` sets the fields it means to set, one at a time, and the
test bites a body before every dose and asserts the bite survived.

The rule generalises past this one method: `RestoreToFullHealth`,
`RecalcAllWithNeighbours`, `createContainersFromSpriteProperties` and anything
else whose name is a *summary* are bundles of writes chosen for somebody
else's feature. `tools/javadis.py` lists what is in the bundle. Read it before
reaching for the short call, especially when the difference between "does what
I asked" and "does more than I asked" is invisible from outside.

### Player mod data a client writes is not the server's

**New in this mod, and it was a live multiplayer bug in probes that no test
could see.** A player's return point -- where they beamed up from, which is
where a player standing in the cabin *is* as far as the map is concerned -- is
player mod data, and the client writes it, on the client's own copy of the
player. A dedicated server has its own `IsoPlayer` for that player, and that
write never reached it. So on a server `Ship.worldOrigin` asked about anybody
aboard had no answer: a probe launched from the sensor console was refused for
want of a position fix, and the downed ensign's distress call had nowhere to
be measured from.

Single player could never show it, because there the client's player and the
server's player are one object. It surfaced only when the first two-client
test of the ensign asked the server where the crew were.

- **The fix is to write it on both sides, where each side already has the
  answer.** The server's `move` handler runs *before* a beam up or a walk
  through the hatch, while the player is still standing where they are
  leaving from -- so it records the return point on the server's copy there.
  The client's own write is untouched.
- **Ask of every piece of player mod data: which machine wrote it, and which
  machine reads it?** If the answers differ on a server, something is reading
  a value that was never sent. This is *A setter's own sync may be one-sided*
  and *Single player cannot test a fix that both ends apply* seen from the
  data's end rather than the code's.
- `ensign_multiplayer()` asserts the server's answer for a player aboard, and
  launches a probe from the cabin on a server.

### A timed action is rebuilt on the server by its name and its parameters

**New in this mod, with the PADD -- its first timed actions.** In build 42 a
client does not run a Lua timed action by itself. Three facts, all from the
bytecode, and each one a way for an action to do nothing in multiplayer while
working perfectly in single player:

- **Every one goes to the server.** `LuaTimedActionNew.start()` calls
  `ActionManager.createNetTimedAction` on a client (bci 60-101), and the
  server rebuilds the action by looking its **global class name** up
  (`NetTimedAction.parse`, bci 75-167). So the class has to be a global, in
  `shared/`, where the server loads it.
- **Its arguments are its own fields, by `new`'s parameter names.**
  `NetTimedAction.set` walks `Prototype.locvars` and `rawget`s each name off
  the action. `new(character, padd, book)` storing `o.item = book` sends the
  server a nil book, and the rebuilt action is simply invalid. Store every
  parameter under exactly its own name.
- **`complete()` never runs on a client** (bci 34), and `perform()` runs on
  the client. So the state change is `complete()`, followed by the sync that
  gets it back to the player (`syncItemModData`, `sendSyncPlayerFields`), and
  `perform()` is for notes and sounds.

`tests/pz_sim.lua` models all three: single player runs the whole action in
one process, a client sends it by class name with arguments read by
`debug.getlocal` on `new`, and the server rebuilds, validates and completes
it. A mutation that renames one parameter is caught. `PADD.md` section 7.

### A setter's own sync may be one-sided

**New in this mod.** `IsoDoor.setLockedByKey(b)` does sync itself, which makes
it look like the whole job -- and the branch that does it is:

```
 24  getstatic  GameServer.server
 27  ifne       -> 55            <-- on a server, skip the sync entirely
 43  invokevirtual  IsoDoor.sync(3)
```

So the engine syncs a lock change made on a **client** and not one made on the
**server**. A lock is world state, so by this document's own first rule the
server is the thing that changes it -- which is exactly the process where that
code does nothing. The door opens on the server and stays shut on every
screen.

`obj:sync()` is the call that covers both: on a server it writes a
`SyncIsoObject` packet to every connection, on a client it sends one to the
server, in single player there is nobody to tell. Public, with vanilla Lua
call sites on both sides (`server/ClientCommands.lua:780`).

**The general shape: "it syncs itself" is a claim about one side.** Whenever a
setter is documented -- or observed -- to replicate, check which process it
was written for. This mod has now been bitten by the mirror image of this
twice: `addFluid` really does sync from the server, and a vehicle's mod data
really does not reach clients at all.

### Single player is neither a client nor a server, and the engine assumes it is one

**New in this mod, and it shipped: the ship would not take off.** A pilot sat
at the controls, the radial menu offered *Take her up*, the server logged
`clearing her for level 3` -- and nothing happened, four times, with no error
anywhere. The cause was one line added to `takeoffGranted`:

```lua
if not ownsPhysics(vehicle) then return end   -- vehicle:isLocalPhysicSim()
```

`isLocalPhysicSim()` is public, obvious, and exactly what it says. It is also
**unanswerable in single player**:

```
BaseVehicle.<init>        netPlayerAuthorization = Authorization.Server
constraintChanged()   14  getstatic  GameServer.server
                      17  ifeq -> 92        <-- off a server: set nothing
                      89  authorizationChanged(getDriver())   ; -> Local
isLocalPhysicSim()     0  getstatic  GameServer.server
                       3  ifeq -> 14        ; a server: is it still Server?
                      14  authorization == LocalCollide || == Local
```

Only a server ever hands a vehicle's authorization to a driver, so off a
server it is never anything but `Server`, and `isLocalPhysicSim()` is
permanently false. **Vanilla never asks it in single player either** --
`isBrakePedalPressed()` consults it only inside its `GameClient.client`
branch and otherwise goes straight to the controller, which is the tell.

Three things follow, and the first is the general one:

- **A method written for the client/server split has a third caller nobody
  tested.** `isLocalPhysicSim`, `isLocalPlayer`, `isRemoteZombie`,
  `sync()`, `setLockedByKey` -- all of them mean something in two of the
  three setups and something accidental in the third. This file already has
  *A setter's own sync may be one-sided* and *Single player cannot test a fix
  that both ends apply*; this is the same fault from the reading side.
  **Before guarding anything on one of them, ask what it answers in all
  three.**
- **Ask the question the guard is for, not the one the engine can answer.**
  The goal was "only one machine moves her". In single player that machine is
  this one -- there is no other -- so `ownsPhysics` says so itself and asks
  the engine only when there is a server to disagree with (*A guard is only as
  good as the goal it was written from*).
- **And the simulation was kindest about the broken case.**
  `tests/pz_sim.lua` answered `SIM_ROLE ~= "server"`, which is true for single
  player, so the whole flight suite passed against a build that could not
  leave the ground. *The simulation has to be as unkind as the engine* -- and
  the place to look first is wherever the stub's answer is a one-liner about
  `SIM_ROLE`.

The silence was the other half of it. Both of that handler's early returns
said nothing, so the log could not tell "granted and refused" from "never
asked", which `PILOTING.md` section 6 had already written down after the same
thing happened to `F.land`. Both say which one they took now.

### Single player cannot test a fix that both ends apply

**New in this mod, and it hid three mutations behind a green suite.** The
EMH's cure is written in two places on purpose: the server clears the body's
infection flags, and the patient's own client clears the same flags again on
`emhCured`, because `syncBodyPart` carries `BodyPart` fields only and the
`BodyDamage` flags and the moodle do not ride it.

In single player those are **one process**. `Net.toClient` runs the handler
directly, so the client's clear lands on the same table the server just wrote
-- and three mutations that deleted the server's half entirely (the infection
time, the mortality duration, the fake-infection flag) left a suite that could
not tell, because the client repaired every one of them a millisecond later.

The rule is not "test it in multiplayer" -- it is narrower and more useful:

- **Whenever two processes both write the same field, single player proves
  only that *somebody* wrote it.** Which one is doing the work is invisible
  until they are separate machines.
- So the assertion has to name the process: `emh_multiplayer()` reads the
  **server's own copy** of the patient after a cure, which is the copy that
  matters, because the server is the machine that runs `BodyDamage.Update`.
- And the mirror of it is worth keeping in mind: a check that runs on the
  client is not evidence about the server either. The moodle check is
  client-side and correct there; the flags check had to move.

This is the same shape as *A check that runs after a self-healing pass checks
the healing* -- something else was quietly covering for the code under test --
one process apart rather than one pass apart.

### A derived flag that latches needs clearing at both ends

**New in this mod.** The zombie infection is kept in two places with nearly
the same names, and they are not two copies of one fact -- one is *derived*
from the other, once, and then sticks:

| | |
|---|---|
| `BodyPart.IsInfected()` | the virus in one limb |
| `BodyDamage.isInfected()` | the virus in the person |

`BodyDamage.Update()` walks the parts and sets the body flag when any of them
is infected (bci 280-300) -- and **skips that walk entirely once the flag is
true** (bci 271). So it is a one-way latch over a derived value, and there are
exactly two ways to get it wrong, both of which look like a working cure from
outside:

- **clear the body flag alone** and the next tick re-derives it from the parts
  that are still infected. The player is cured for one frame;
- **clear the parts alone** and the latch never drops, because the code that
  would have dropped it is the code that is skipped.

Both have to go in one pass, and the test has to **tick the body afterwards**
-- a check taken on the same frame passes for either mistake.

There is a third end to it, and it is the one that would have reached a
player. The infection **moodle** is not a flag at all: `CharacterStat
.ZOMBIE_INFECTION` is written from inside the countdown at bci 2007-2014, and
the countdown is gated on `isInfected()` at bci 1877. Cure the player and that
block stops running -- so the last value it ever wrote is the value that stays
on screen. A perfect cure, with the moodle still saying you are dying.

**And none of it rides the sync.** `syncBodyPart(part, mask)` carries
`BodyPart` fields only, so the body-level flags and the moodle do not reach
the patient's client with the limbs. The EMH sends them a message and their
own client clears its own.

The general shape: **before clearing a flag, ask what derives it, how often,
and whether anything stops deriving it once it is set.** A value that is
recomputed is safe to write; a value that is recomputed *until it latches* is
two writes, and a value drawn from inside a loop that your fix switches off is
three.

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

### A getter named for an axis may be one corner of a decomposition

**New in this mod, and it made the first two-player flight unflyable while
every test passed.** The report was *"in hover it snaps us back basically
forever, but if I go backwards it seems to work"*, and the cause was two
`BaseVehicle` getters that read exactly like what a pilot means by pitch and
roll:

```lua
if math.abs(vehicle:getAngleX()) < 4 and math.abs(vehicle:getAngleZ()) < 4 then
    return false      -- she is level
end
vehicle:flipUpright()
```

`getAngleX()` does not read a field. It decomposes the vehicle's whole rotation
with JOML's `getEulerAnglesXYZ` and multiplies by 180/pi, and the X of that
decomposition is `atan2(2(xw - yz), 1 - 2(x^2 + y^2))`. For a ship that is dead
level and turned by yaw alone that is `atan2(0, cos yaw)` -- **exactly 180 once
the heading is more than a quarter turn from the identity**, and the same for
Z. So the test was true in one half of the compass and false in the other, for
a ship that was level in both.

And `flipUpright()`, the obvious remedy, is `setAngleAxis(**0**, _UNIT_Y)`
followed by `setWorldTransform` -- an angle of *nothing*, which is the identity:
it discards the heading along with the pitch and the roll, by teleporting the
physics body. Turn her past ninety degrees and she was hauled back to her spawn
heading ten times a second, losing her velocity each time. Reverse never leaves
the safe half of the compass, which is why reversing worked.

Four things worth carrying:

- **A three-number decomposition is not three independent facts.** Euler angles
  have a representation for every rotation and more than one for some of them;
  "is X small" is a question about the representation, not about the ship. Ask
  something frame-independent instead -- here, the Y of the ship's own up
  vector, `cos(az)cos(ax) - sin(az)sin(ay)sin(ax)`, which is 1 level and -1 on
  her back at every heading.
- **Read what the correction writes, not what its name promises.** This is *A
  convenience method is a bundle of writes somebody else chose* again, one
  argument wide: the bundle `flipUpright` applies includes the yaw, and the
  name does not say so.
- **The exposure allow-list decides what a fix can be made of.**
  `zombie.core.physics.Transform` and `org.joml.Vector3f` are on
  `LuaManager$Exposer`'s list; **`org.joml.Quaternionf` is not**, and `Transform`
  hands out only its origin. So the rotation cannot be read or written
  directly, and `BaseVehicle.setAngles(F,F,F)` -- degrees, built with
  `Quaternionf.rotationXYZ` in Java -- is the whole reachable surface. Grep the
  list before designing the repair, not after.
- **And the simulation was kinder than the engine.** `pz_sim.lua` stored the
  three angles as fields and handed them back, so the 180 artefact could not
  occur there at all, and its `flipUpright` kept the heading the engine throws
  away. It keeps a real quaternion now and decomposes it the same way. Hole
  number nine; see *The simulation has to be as unkind as the engine*.

`PILOTING.md` section 4 has the full derivation.

### A guard gated on loaded ground never sees the case it exists for

**New in this mod, and it stranded a crew in the second two-player session.**
The server's watchdog -- nobody aboard the hovering shuttle, so send her back
up -- lived inside `if found then`, where `found` is the ship's vehicle as the
cell lists it. Chunks stream only around players, so `found` is nil exactly
when nobody is near her, which is exactly the case the watchdog exists to
catch. A crew who beamed down and walked away left her flying for the life of
the world.

Nothing else was wrong, and everything else looked wrong: the hatch refused
("in flight"), recall refused ("in flight"), and a call-down spawned her on the
ground and every client immediately paved a plane under her and lifted her back
into hover, because `flying` was still set. Four bug reports, one line.

- **Ask what a guard's own inputs are nil for.** A nil was not an edge case
  here, it was the subject. Anything conditioned on "the world near X is
  loaded" has a blind spot shaped exactly like "nobody is near X" -- and for a
  watchdog, that shape is usually the whole job.
- **The related question: can this run at all where it matters?** The same
  file already gets this right twice on purpose -- `serviceCures` and
  `serviceProbe` sit *outside* the cabin-loaded branch, with a comment saying
  so, because a cure and a probe are logical jobs with no world object behind
  them. Whether a ship is still flying is the same kind of fact.
- **And a stuck state needs a manual way out.** The crew's own instincts --
  recall her, call her down -- were both right and both refused. They work now,
  refused only while somebody is actually aboard, and the refusal names itself
  rather than falling through to "not enough room".

The simulation was honest for once (`cell:getVehicles()` already filters on
`SIM.loaded`); the *test* was the kind one, because the pilot beamed down to a
return point a few squares away and her chunk never unloaded. Which is the
same lesson one level out: **a scenario that never reaches the condition is not
a test of it**, so `flight_alone()` asserts `TREK.Vehicle.ship()` really is nil
before it believes anything that follows.

### A door with no handle on the inside

**New in this mod.** Flight lets the crew go aft to the cabin and come back --
that sentence had been in `PILOTING.md` since the feature was built, and the
second half of it was never implemented. Going aft in flight worked; coming
forward did not exist. The hatch is shut while she hovers, *Step outside* is
hidden for the same reason, and the aboard menu's only other way off her is a
beam down. A pilot who stepped through to read the helm could never fly her
again.

It is not that anything refused. There was simply no option, and an absent
option is the hardest kind of missing feature to notice from the source,
because nothing in the diff is wrong. The tell was in the docs: a claim about
a round trip, with code for one direction.

- **When you add a one-way move, write the return leg in the same pass** --
  or write down that there is not one.
- **A prose claim about a round trip is a check nobody runs.** This one had
  survived two documents and a test suite. `flight_alone()` now goes aft and
  comes forward again.

### An offer the ship cannot keep is worse than a smaller offer

**New in this mod.** Flight shipped with four altitudes: `FlightMin` 1,
`FlightCruise` 3, `FlightMax` 4, and *Climb* and *Dive* on the radial menu. In
play only the ground and level 1 ever behaved, so three of the four rungs were
a control that appeared to do nothing -- the failure mode this file already
names under the speed steps that all clamped to the same number.

It is one altitude now, `C.FlightLevel = 1`, with no climb, no dive and **no
`setAltitude` command on either side**. Leaving the command in as a no-op, or
as a ceiling that refuses politely, would have been a request with a handler
that quietly does nothing.

Two things came out of doing it that generalise:

- **Ask why the one that works, works.** `BaseVehicle.update()` accepts a
  height when a floor exists at that level *or the one below*. At level 1 the
  one below is the ground, so the engine's floor test is satisfied by Kentucky
  and the sky plane only has to make the square exist; at level 2 and above the
  plane is the only thing holding her up and every square of it has to be laid
  and stay laid. Level 1 was not arbitrarily the survivor.
- **A ceiling that comes down does not tidy up after the old one.**
  `C.SkyLitterTop` is still 4, deliberately not following `C.FlightLevel`: a
  floor is a saved world object and the flights that went to level 4 left
  theirs in somebody's world. Same shape as `C.LegacyCabin` -- *write the old
  extent down*.

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

### A blade is its silhouette, and only a render will tell you what it is

**New in this mod, and it cost three redraws in one sitting.** Every new
weapon here was built from a profile that read correctly in the source and
came out as something else entirely:

- the mek'leth, a straight blade with a bellied edge, rendered as a **machete**
  -- a shape build 42 already ships four of. What makes it a mek'leth is that
  the whole blade leans *forward* and the spine goes concave near the tip;
- the ushaan-tor's hook was made by tilting its back edge over the last two
  sections. That does not curl anything, it cuts a corner off, and it rendered
  as a cleaver with a chamfer. A hook is the **centreline moving sideways**
  while the blade thins -- the metal has to go somewhere;
- the lirpa's counterweight came out **wooden**, because the shaft asked for a
  wood recolour of a texture strip the weight was also using.

None of those is visible in a section list. All three took one look at
`tools/preview_model.py` output. **Render it and look** is already in this file
for the hull; it applies at least as much to a weapon, where the silhouette is
the entire identity.

And judge an icon **against the set**, not alone (*Vet icons with
tools/vet_icons.py*). Rendered upright, the lirpa filled **11%** of its 32px
frame -- four pixels of content -- the mek'leth 22%, the ushaan-tor 30%, where
the bat'leth is 60% and the food icons 65-82%. On the diagonal, which is how
vanilla draws every blade, they are 71%, 57% and 49%. A long thin weapon in a
square frame is mostly empty, and that is a fact about frames, not about the
weapon.

`tools/bladekit.py` holds the shared machinery -- section lists extruded up the
Y axis, the common texture sheet, the icon rendered from the finished mesh.

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
  stat and scales nothing.** `tools/meshbbox.py` measures any `.x` file, ours
  or the game's, so this bracket is checkable rather than remembered:
  `python tools/meshbbox.py --vanilla spear`. And the bracket to sit in is not the one you would
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

### An imported mesh has no author, and three of its properties are accidents

**New in this mod.** The hull and the Doctor are both imported rather than
built out of `MeshBuilder` calls -- a GLB from a generator, through
`tools/import_gltf.py`. That is the right route for anything with a shape
worth more than a script can describe, and the cost is that nothing about the
result was *decided*. Three things in particular, all of which looked finished
in the source and all of which one render settled:

- **It faces the camera that made it.** An image-to-3D model is built looking
  down its own +Z, which this engine reads as due north -- so the Doctor
  stood in the sick bay with his back to the entire cabin. There is no way to
  know that except by looking, and no reason the generator would have done
  anything else. `import_glb` takes a `yaw` now, and he is turned to face
  south, which is the facing every sprite set in `C.Sprites` falls back to and
  the one the isometric camera shows the front of.
- **Its UVs are an atlas, so a texture row is not a line on the model.** The
  hologram's scanlines were written the obvious way -- one texel row in four,
  dimmed -- and rendered as **wood grain**: the islands of an auto-unwrapped
  atlas lie at whatever angle packed best, so a row of the sheet is a
  different diagonal on every patch of him, and at 1024 texels over a figure
  1.25 tiles tall the pitch aliases as well. The fix is to stop working in
  texture space: `gen_emh.py` rasterises the mesh's own UVs once to give every
  texel the *world height* of the surface it lands on, and bands on that.
  Anything that has to be level, plumb or aligned on an imported model needs
  the same treatment.
- **It has to be fitted by the dimension that means something.** A hull is
  fitted into a parking space, so `min(width/x, length/z)` is right for it. A
  person is fitted under a deckhead, and scaling a standing figure by its
  footprint makes its size an accident of how wide its shoulders happen to
  be. Hence `target_height`.

And one thing that is not about imports at all: `preview_model.py`'s parser
was **dropping the last vertex of every mesh it read**. A `.x` list ends
`a;b;c;;` and the non-greedy match stopped inside that pair, leaving the final
entry one semicolon short of the per-entry pattern. On a generated mesh the
last vertex is usually unreferenced and nothing happened; on an imported one a
face used it and the previewer threw. It now puts the separator back and
**fails loudly when the count it parses does not match the count the file
declares** -- because a previewer that quietly reads a different model from
the one on disk is worse than no previewer at all.

### A garment is reached by GUID, and an unknown GUID is null

**New in this mod, and it is the seventh face of "present, drawn and inert".**
A clothing item's `ClothingItem = X` does not resolve by name. The engine
looks `X` up as a **GUID**:

```
OutfitManager.getClothingItem(String)
   0  ZomboidFileSystem.getFilePathFromGuid(guid)
   9  ifnonnull -> 14
  12  aconst_null ; areturn      <-- unknown guid: null, and no more
```

and the table it consults is merged from every active mod by
`ZomboidFileSystem.loadFileGuidTable`, which reads each mod's file **inside a
catch that only reaches `ExceptionLogger`**. So a uniform whose GUID row is
missing, misspelt, or in a table that failed to parse still equips, still
weighs what it says, still insulates, still gets dirty and **draws nothing at
all**, with nothing in the log.

Every static check in this repository can pass on that: the item exists, the
XML exists, the mesh and the texture are on disk, the translations resolve.
They prove the files agree *with each other*, not that the engine found them.

- **The mod ships its own table**, at `TrekShuttle/42/media/fileGuidTable.xml`.
  `loadFileGuidTable` walks `getModIDs()` and merges from the mod's common dir
  *and* its version dir (bci 265-310), so that path is supported rather than a
  trick.
- **`FileGuidTable.mergeFrom` is a plain `ArrayList.addAll`** with no
  de-duplication at all. A GUID or a path that collides with one of vanilla's
  1,795 is resolved by whichever row is found first, which is not a thing to
  leave to chance. `tests/test_assets.py` checks both directions.
- **Generate the row with the thing it points at.** `tools/gen_uniform.py`
  writes the texture, the clothing XML and the GUID row in one loop, because a
  join that fails silently is the last join anybody should be hand-editing.
- **And read it back in game.** `TREK_Uniform()` asks the engine for each
  garment's `ClothingItem` and logs the model and texture it came back with.
  That is the same answer `B.stockReport()` gave for the empty lockers, and
  it is the only kind of check that has ever caught this shape.

### Ask the asset which way round it is; do not derive it

**New in this mod, and one render caught it.** The combadge goes on the
wearer's left breast. Which side that is was worked out from the geometry --
the rigs are Y-up and face -Z, so `left = up x forward = Y x (-Z) = -X` -- and
the first render had it on the wrong breast.

The rigs carry a **named skeleton**, and it answers the question outright:

```
Bip01_L_UpperArm   mean x = +0.128      Bip01_R_UpperArm   mean x = -0.128
Bip01_L_Hand       mean x = +0.369      Bip01_R_Hand       mean x = -0.369
```

The wearer's left is **+X**. No handedness convention, no cross product, no
argument: the file says so, in the bone names, and reading the skin weights
took four lines.

The general shape, and it is the same one as *The bytecode is the
documentation* a level up: **when an asset encodes the answer, read the asset.**
A mesh's bone names, a tile's properties, a script's own module -- all of them
are facts on disk, and all of them beat a derivation that is right only if
every assumption under it happens to hold. The derivation above was wrong for
reasons that are still not interesting.

And the corollary about how it was found: a badge on the wrong breast is
invisible in the source, invisible in a texture, and obvious in one picture.
**Render it and look**, for the fourth time in this file.

### One texture on two bodies has to mean the same thing on both

**New in this mod.** A clothing item names one `textureChoices` path and *two*
models, male and female. The sheet is shared, so a texel's meaning has to be
the same on both rigs -- and if it is not, the garment is right on one body and
scrambled on the other. Which is a character the author may simply never have
made.

`tools/gen_uniform.py` therefore builds its region map from **both** rigs and
fails when they disagree. The first version of that guard measured the raw
distance between the two rigs' positions at each shared texel and failed the
boilersuit at 0.077 -- which turned out to be the collar sitting five
centimetres off-centre on Bob and centred on Kate. Two bodies of different
shape sharing one layout, which is exactly what vanilla ships.

The guard was measuring millimetres when the question is **which panel**. It
counts texels that land in a different *region* on the two rigs now: the duty
rigs differ at 1.33% (seams), the dress rigs at 0.00%. Same lesson as *A guard
is only as good as the goal it was written from*, arrived at from the other
end -- the guard was accurate about the geometry and wrong about the goal.

Two smaller things from the same pass, both of which produce a plausible file:

- **An auto-packed atlas needs its islands bled outward.** Everything between
  them is transparent, the sampler does not respect island boundaries, and
  filtering along an edge therefore mixes the garment with nothing -- a dark
  fringe down every seam, on the sleeve heads and the collar, which is where a
  person looks. Vanilla's own clothing textures are padded; ours dilates four
  passes.
- **Borrowed cloth detail brings the garment it was painted for.** The rigs
  are unwrapped for garments that already have creases and shading in the
  right places, so reusing the vanilla texture's luminance gives fold detail
  for nothing. It also gives you *their garment*: clamped to a fraction of its
  range the boilersuit's zip, breast pockets and cuff seams still came
  through, and the first thing said about the finished uniform was that it
  looked like a jumpsuit with jumpsuit pockets. The shading is computed from
  the mesh instead now -- an outward normal approximated from position, lit by
  one lamp -- which is the same amount of code and borrows nothing.

  The sting is that it *looked* fine in isolation. A texture that carries
  somebody else's hardware is not a rendering fault and no check can see it;
  only somebody looking at the thing and saying "why does it have pockets".

### A mutation that does not apply proves nothing

**New in this mod, and it cost a wrong conclusion for about a minute.** The
mutation harness edits a source file, runs the checks, and restores the file.
One mutation reported **MISSED** -- a uniform with no female model sailing
past a check written specifically to catch it -- and the check was fine. The
search text in the harness had a backslash wrong, matched nothing, and the
suite passed against **unmutated code**.

A mutation that does not apply looks exactly like a check that does not work,
and it points at the wrong thing: the instinct is to go and fix the check.

- **Assert the file actually changed.** `assert new != orig` before writing is
  one line and it converts a silent false negative into a loud one.
- It is the same rule as *A check against an empty set is not a passing check*,
  one level up: the mutation harness is itself a check, and a check that had
  nothing to check is not a check.

And the other half, which this file already warns about and which bit again:
**restoring a file in text mode rewrites its line endings.** Two files came
back byte-different after a clean run, which looks like corruption and was not
-- earlier edits had put LF lines into CRLF files and the restore normalised
them. Compare the *content* before believing the hash, and keep the whole-file
comparison anyway, because the one time it means corruption is the time it
matters.

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
design/art/ui/torpedo_flight_sheet.png   the projectile over four backgrounds
```

**This applies to procedurally drawn art too, not only to image-model
output.** There is no "raw" for something a script draws — the script is the
raw — but there is still the picture it was *judged* on, and that belongs in
`design/art/` like any other. `tools/gen_torpedo_flight.py` writes its own
contact sheet there on every run, which is the pattern worth copying: the
generator and the vet are the same command, so the sheet cannot go stale.

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

**And the difference cuts both ways.** `math.atan2` exists in Kahlua and was
removed in Lua 5.3, so a bearing written with it works in the game and throws
in the tests. That is the lucky direction -- the harness is stricter than the
engine, so it fails loudly at the desk rather than quietly in somebody's save
-- but the reverse is the same trap as `unpack`, and there is no check that
catches it in general. Where a one-line alternative exists, prefer the one
that is true in both: the sensor menu compares two ratios against
tan(22.5 degrees) and needs no trigonometry at all.

### Write Lua with the Write tool, not shell heredocs

This shell mangles quoted heredocs: an apostrophe in a comment or a `\n` in a
string will break or corrupt the file. Use `Write`/`Edit` for Lua, or a Python
script for surgical patches.

---

## Things that are true about the assets

Meshes and textures are **generated, never hand-authored**:

```sh
python tools/gen_shuttle.py TrekShuttle/42
python tools/gen_helm.py    TrekShuttle/42   # the deleted helm console prop
python tools/gen_phaser.py  TrekShuttle/42
python tools/gen_batleth.py TrekShuttle/42   # mesh, texture and icon
python tools/gen_mekleth.py TrekShuttle/42        # and lirpa, ushaantor
python tools/meshbbox.py --vanilla spear          # measure vanilla, or ours
python tools/gen_poster.py  TrekShuttle/42
python tools/gen_reticle.py TrekShuttle/42        # the torpedo reticle
python tools/gen_medical.py TrekShuttle/42        # the medical set's three sounds
python tools/gen_replicator.py TrekShuttle/42     # the machine, its sound, its renders
python tools/gen_dilithium.py TrekShuttle/42      # the crystal's icon
python tools/gen_warpcore.py TrekShuttle/42       # the warp core and its renders
python tools/gen_emh.py     TrekShuttle/42       # the Doctor: mesh, texture, portrait, chime
python tools/gen_uniform.py TrekShuttle/42        # the six uniforms: textures, icons, clothing XML, GUID table
python tools/gen_map_symbols.py TrekShuttle/42    # the world-map contact glyphs and their registration
python tools/gen_ensign.py  TrekShuttle/42        # the downed ensign: six baked figures (after gen_uniform)
python tools/gen_padd.py    TrekShuttle/42        # the PADD: mesh, texture, icon
python tools/gen_torpedo_flight.py TrekShuttle/42 # the torpedo in flight
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

### A pose can be baked out of the game's own files

**New in this mod.** A static model cannot play an animation -- but the game
ships its characters, its clothing rigs and its animations as text `.x`, and
`tools/xskin.py` reads all three and applies linear-blend skinning at one
frame. That is how the downed ensign is a vanilla body in the mod's own
uniform, sitting exactly as `Bob_SitGround_Pain_Stomach` sits, with nothing
modelled by hand. Three things the first bake settled, all in `ENSIGN.md`
section 6:

- **the rotation keys are stored conjugated** relative to the Direct3D
  reading, and a wrong guess bends every joint backwards without an error --
  so it is measured against a file whose first key is its own frame pose,
  every run;
- **a body's frame matrices are a walk, not the bind pose**; the bind pose is
  only in the SkinWeights offsets;
- **one texture per static model** means building an atlas, and every source
  rig's UVs have to be wrapped inside their own quadrant.

Render the result and look, as ever: the crew cut turned out to be a cap with
the back of the head bare, which a hunched pose shows first, and three
lying-down poses all read as a corpse.

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
| **A new blade reads as a machete / cleaver / stick** | Its silhouette is not saying what it is. Render it (`tools/preview_model.py`) -- this is invisible in a section list. See *A blade is its silhouette*. |
| **A weapon icon is a thin sliver next to the rest of the set** | It is being drawn upright in a square frame. Tilt it, as vanilla draws every blade; `tools/vet_icons.py` shows the whole set and the fill percentages tell you at once. |
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
| **The shuttle snaps back to one heading and will only fly in reverse** | Something is levelling her off with `flipUpright()`, which is `setAngleAxis(0, Y)` -- the identity, heading and all -- on a test that reads `getAngleX()` as pitch. That getter is 180 for a *level* ship turned more than a quarter turn. See *A getter named for an axis is one corner of a decomposition*. |
| **The radial menu offers Climb or Dive** | Something has grown the altitude ladder back. There is one flight level (`C.FlightLevel`) and no `setAltitude` command; `tests/test_multiplayer.py` fails on either. |
| **A hovering shuttle nobody can reach: the hatch says "in flight", recall is refused, and calling her down brings her back in hover** | `flying` is stuck true. The watchdog that clears it must run whether or not her chunk is loaded -- see *A guard gated on loaded ground*. A world reload also clears it (`OnInitGlobalModData`). |
| **A pilot goes aft to the cabin in flight and cannot get back to the cockpit** | The aboard menu's *Forward to the cockpit* is missing or its beam is not being serviced. See *A door with no handle on the inside*. |
| **The shuttle vanishes out of the sky** | Working as designed: nobody has been aboard for `C.FlightPilotGrace` checks, so she went back up rather than dropping onto whatever was underneath. `landed` is false and she can be called down. The log says `the shuttle has gone back up`, and the crew get a note. |
| **A ship parked in the sky for ever** | Flight ended without `Sky.clear()`. The floors are world objects and they are saved. `s.skyAt` is how they get lifted; if that was lost, they are permanent. |
| **An explosion kills things and nothing is seen** | In build 42 the visible part of an explosion *is* the fire and the smoke; there is no separate effect. `FireStartingChance`, `FireRange` and `SmokeRange` are set in **two** places — the item script and the Lua — and `triggerExplosion()` skips any mode whose range is 0 entirely. See `PHOTON_TORPEDOS.md`. |
| **A locked door opens for the host and stays shut for everyone else** | The lock was changed on the server and never synced. `setLockedByKey` fires its own sync only when it is *not* the server; call `obj:sync()`. See *A setter's own sync may be one-sided*. |
| **An item heals more than it was meant to** | A convenience method. `BodyPart.RestoreToFullHealth()` clears the bite as well, and nothing anywhere reports it. See *A convenience method is a bundle of writes somebody else chose*. |
| **An appliance in the cabin will not switch on** | Its square has no electricity and never will: `setHaveElectricity` sets nothing and `haveElectricity()` means a generator is running in the chunk. Power the *device* instead -- `TREK_Power()` reports each one. |
| **A television, stove or switch is drawn and cannot be used** | It was built with `IsoObject.new`, so it is an `IsoObject` wearing that sprite. The engine picks the class from what built the object, not from the picture. See *A sprite is not the object the engine builds from it*. |
| **A fitting refuses to go somewhere that is obviously empty** | Something on that square is being treated as an obstacle that is not one. Wall objects and lamps carry neither `solid` nor `solidtrans`; read `tools/_catalog/tiles.json`, do not assume. |
| **Furniture standing in the black void outside the hull** | Cabin geometry moved and nothing named the old squares. `U.clearSquare` keeps tagged objects and dropped items by design, so a shrink is a migration. `grep "refit:" console.txt`. |
| **A container in the cabin is empty and that is fine** | Five of them are the player's shelves. Only entries with `loot` or `special` are stocked; `wantsStock` is why they do not each log a WARN. |
| **A right-click offers nothing for a mod item** | Build 42 has no script hook for "using" an arbitrary item; it has to be an `OnFillInventoryObjectContextMenu` option. And an entry in that event's `items` is either an `InventoryItem` **or** a stack table with its own `items` list — code that handles one shape silently does nothing for the other. |
| **A panel is fine with a mouse and dead on the Steam Deck** | It is not an `ISPanelJoypad`, or its buttons were never registered with `insertNewLineOfButtons`. Note that vanilla's `ISHealthPanel` *is* one already. |
| **Opening the world map throws `__len not defined`** | A map symbol category with **eight or fewer** symbols. `ISWorldMapSymbols` lays a category out eight to a row and then indexes `joypadButtonsY[floor(rows/2)]`, which is `[0]` for one row -- nil, and `#nil` throws. The error names neither the mod nor the symbol. Put mod symbols in one of vanilla's three categories. |
| **A feature aims at 0,0, or at the far corner of the map** | It is reading the ship's own `s.x, s.y`, which is where she was last *set down* and is `0,0` until she has been. What most callers want is where the **crew** are: `Ship.worldOrigin(player)` -- their position outside, their return point when aboard, the ship only if landed. |
| **A probe, course or mark points outside the map** | Nothing checked the destination was in the playable world. `getWorld():getMetaGrid():isValidChunk(x / 10, y / 10)` is the question, called the way `ISWorldMap.lua:941` calls it. It is a different question from `U.chunkLoaded`. |
| **A menu option works and its submenu is empty** | Nothing tests what is inside a submenu unless the harness models one. `pz_sim`'s `addSubMenu` was a no-op, so every option one level down was invisible; `deepLabels()` and `all()` are what see them. |
| **A bearing or an angle throws only in the tests** | `math.atan2` is Kahlua-only. See *The game runs Lua 5.1*. |
| **A feature is reported broken and every test passes** | Suspect the tests. See *A guard is only as good as the goal it was written from* — a test, a comment and a constant all agreeing with each other is not corroboration if they came from one misreading. |
| **The replicator's menu option never appears** | It is keyed to `C.ReplicatorSpot` (0,5) and its neighbours, so the right-click resolved to a different square -- which is what a model drawn above its own square does every time. `TREK_Replicator()` reports what is standing there. |
| **The replicator refuses everything, with no crystal aboard** | Working as designed: the reserve is one dilithium crystal and nothing refills it for free. Find one -- the tricorder plots them out to twenty tiles. `TREK_Replicator()` reports the reserve and the spares. |
| **The warp core is empty in a save made before it** | The ship is issued its crystals when the cabin is built, once, keyed on the count being absent. Crystals in the *world* are placed when the world is generated, so the loot needs a fresh world too. |
| **A machine in the cabin stands at a crooked angle** | A dropped world model picks its own yaw; see the rule above. The build pass straightens both of them, so it takes a rebuild (or a `C.BuildRev` bump) to reach a machine in an existing save. |
| **A tricorder sweep from the cockpit finds nothing** | Working as designed only if she is on the ground. In the air the sweep reads every level below the seat and the panel says *Ground Survey*; if it does not, the player is not in a shuttle seat -- a crewman aft is in the cabin, which is nowhere near the ground the ship is passing over. |
| **A crystal will not load into the core** | Another mod's item with the same bare type. `getAllTypeRecurse` compares the bare name only, which is not namespaced -- everything counting mod items filters on the full id. |
| **The replicator makes nothing and says the tray is full** | It is: the counter at 0,5 holds 40 units like any locker. Empty it. The count is real -- the server measures the tray after every single item and charges only for what landed. |
| **An item is in the replicator's list and makes nothing** | An obsolete item that slipped the filter; `instanceItem` answers nil for those. The catalogue applies vanilla's own `not getObsolete() and not isHidden()`, so this means a *new* way past it. |
| **The replicator knows nothing, not even the ship's own gear** | `R.seedDefaults()` runs on the authority when the world's data loads and needs the catalogue; if `getAllItems()` answered nothing there will be a WARN saying so. |
| **The EMH's option is missing at the wall panel** | It is keyed to `C.EmhMenuSpots`, a named set, because a right-click lands on the floor square under the cursor. `TREK_EMH()` reports whether he is standing there at all. |
| **The ship says the Doctor is up and the sick bay is empty** | `B.serviceEMH` brings the deck into line with `s.emh` in both directions and runs as a build phase *and* on the per-minute tick, so this is self-healing -- unless the build phase was removed, which is what `TREK_Rebuild()` would then expose. |
| **Two Doctors** | Something placed without counting first. A world item is saved and `U.clearSquare` keeps world items by design; `B.emhAt` is the count and the service pass removes the lot and projects one. |
| **A cured player still has the infection moodle** | The moodle is written from inside a countdown gated on `isInfected()`, so curing them stops its only writer and the last value it wrote stays on screen. The patient's own client has to reset `CharacterStat.ZOMBIE_INFECTION`; no packet carries it. |
| **A cure lands and the infection comes straight back** | Only one of the two levels was cleared. `BodyDamage.isInfected` is a one-way latch re-derived from the parts, so both have to go in one pass -- and a test that does not tick the body afterwards cannot tell. |
| **A cured limb is infected and bleeding** | One-argument `SetBitten(false)`. It clears the bite and then infects the limb regardless, and vanilla's admin health cheat calls it that way twice. |
| **The Doctor will not come up at all** | The reserve is empty and there are no spares. He runs on the same dilithium as the replicator, which four comments in this repository promised before he existed. |
| **A uniform equips, weighs something and the character is naked** | Its `ClothingItem` resolved to null: the GUID is not in the merged table, or the mod's `fileGuidTable.xml` did not ship. Nothing is logged. `TREK_Uniform()` says which. |
| **A uniform looks right on one character and scrambled on another** | Male and female share one texture and the two rigs disagree about what a texel means. `tools/gen_uniform.py` fails above 2%; if it passed, the thresholds moved. |
| **A dark fringe down every seam of a garment** | The texture's UV islands are not padded, so filtering along an edge mixes the garment with the transparent gutter. `dilate()` in the generator. |
| **A combadge, pocket or patch is on the wrong side** | Handedness was derived rather than read. The rigs' own skeleton says it: `Bip01_L_*` bones sit at **positive** x. |
| **A mutation reports MISSED and the check looks correct** | The mutation's search text may never have matched, so the suite ran against unmutated code. Assert the file changed. |
| **No distress call ever comes** | The ship is not hearing: nobody has boarded since the cabin was built, or there is no dilithium in the core or the reserve. The first call is due an hour of game time after it first hears; the log says `distress: the ship is listening`. See `ENSIGN.md`. |
| **"No transporter lock" on a downed ensign you can see** | The server looked at their square and the figure was not there. The next pass puts a missing figure back. |
| **A probe or a distress call on a server says there is no position fix** | The server has no return point for a player standing in the cabin. The `move` handler writes one before every beam up; a player who has not beamed since the fix will have one after their next. See *Player mod data a client writes is not the server's*. |
| **`ItemContainer.isOccupiedVehicleSeat` NullPointerException, once, on arriving aboard** | Somebody left the shuttle's seat for the cabin without the loot panel being rebuilt: it still showed the seat's container, the move unloaded the shuttle, and vanilla asked a seat whose vehicle was gone. Every seat exit goes through `Core.leaveSeat`, which does what `ISExitVehicle` does -- `vehicle:exit`, `OnExitVehicle`, `ISInventoryPage.dirtyUI()` -- while she is still loaded. `seat_exit()` tests both routes. |
| **A cure is lost although the patient never left** | They went forward to the cockpit. The seats are aboard (`EMH.aboardForCure`), and leaving starts a two-minute grace rather than ending it. |
| **"Not while the shuttle is in the air" when calling her down after beaming off her** | Something counted a player on the ground as seated. `BaseVehicle.getSeat` answers -1, not nil, for somebody who is not in the vehicle -- test `>= 0`. |
| **Half a feature works and the other half is silent** | A wrong engine call on the silent path. `grep -E "\[TREK\] WARN" console.txt` first, always — it is one line and it is the answer. |

---

## Testing

### Static, no game needed

| Check | Catches |
|---|---|
| `tools/luacheck.py` | Lua syntax, via a real Lua VM |
| `tests/test_assets.py` | sprites, items, meshes, textures, icons, sounds (both ways: a clip file that is missing, and a `playSound` the scripts never declared), the phaser's borrowed vanilla references, every translation key, every sandbox option's name, tooltip and value names, and **the whole clothing chain**: an item whose XML is missing, an XML with no GUID row, a GUID disagreeing with the table or colliding with one of vanilla's 1,795, a row for a file that is not there, a model or texture not on disk, a garment with a model for one sex and not the other, a body location the game does not declare, and an armour stat on a uniform |
| `tests/test_stock.py` | items that cannot be created at all; loot that does not spread across its list; containers that do not reach `C.FillFraction` |
| `tests/test_multiplayer.py` | the real code as single player and as a server with two clients: flight (one altitude, no climb or dive, a levelling pass that keeps her heading at every point of the compass, the shut hatch, and the beam that sends her back up), cabin build and stock reaching every client, ownership and crew, transporter charges, landing round trips, ghosts, shields pushing only local zombies, the torpedoes, the medical set (including that a dose leaves a bite and the infection alone), the replicator (the catalogue's filter, patterns, the reserve, a counted tray and all three sandbox values), the EMH (the menu, one Doctor standing square, a treatment that leaves the bite, a cure that clears both levels and the moodle for a crystal and twelve hours, consent raised on the patient's screen and nowhere else), a client editing the world or ship state, commands without handlers, missing file guards, role-gated setters, every `deny()` reason having words behind it, any logged `WARN` |
| `tests/test_helm.py` | the mod's panels -- the helm console, the tricorder's contact plot, the replicator and the EMH's dialogue -- for throws, draws out of bounds, clipped labels, dead controls, controller-unreachable buttons |
| `tests/test_layout.py` | fittings outside the hull, on the pad or stacked; containers not flagged as containers; loot lists that do not exist; `special` names with no rule behind them; the replicator's berth, the core's square and the EMH's; **no fixture's menu squares containing another fixture's own square or the pad**; the Lua drifting from the `.tbx`; multi-tile offsets vs `SpriteGridPos`; the footprint against the mesh |

`test_stock.py` stubs the engine **the way it really behaves** — `instanceItem`
present, `InventoryItemFactory` nil — and its first assertion is simply that an
item can be created. Against the old code that assertion prints `0 items` and
fails. Keep it first: with item creation broken, every other check in the file
still passes on an empty container, which is exactly how this reached the game
twice.

**Mutation-test anything new, and run one pass at a time.** The harness edits
a source file, runs the checks, and puts the file back in a `finally`. Two
passes at once share those files: the second reads a file the first has
already mutated, calls that the original, and restores *that* when it is
done. It happened here -- two runs overlapped and left `if false then` in a
refusal and a missing `straighten` in the build, with a green suite on top of
them, because the checks for both had been mutated out along with the code.

The cheap guard is a list of every line a harness touches, checked back
against the source afterwards; the expensive one is reading a diff line by
line. Do the first.

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
| `TREK_Power()` | Top the ship's devices up and log each one's cell -- and whether it is a device at all |
| `TREK_Shields()` | Report the shields; `TREK_Shields(false)` / `(true)` asks to set them |
| `TREK_Rebuild()` | Tear down and regenerate the cabin, restocked. Stand aboard. **Destroys contents.** |
| `TREK_Beam()` | Beam up if outside, down if aboard |
| `TREK_Room()` | Report whether the ship could land here and what is in the way (this client's view) |
| `TREK_Phaser()` | Report phasers found on you and recharge them |
| `TREK_Ghosts()` | Sweep hulls waiting to be cleared, and strays near you |
| `TREK_Charges()` | Log whether beams are rationed on this server and your charges |
| `TREK_Replicator()` | The sandbox mode, the reserve, the ship's spare crystals, how many patterns the ship holds, and the catalogue's size |
| `TREK_Uniform()` | Whether each uniform's `ClothingItem` resolved through the GUID table, and the male model, female model and texture it came back with. **The first thing to run the first time the wardrobe is carried into a world** -- a garment whose GUID is missing wears perfectly and draws nothing |

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

Version **1.4.1**, build revision **28**.

`modversion` in `mod.info` and `C.Version` in `TREK_Config.lua` are the same
number, and `tests/test_assets.py` fails if they are not -- they had drifted a
whole release apart (1.4.0 against 1.3.0) and the log was reporting the version
before the one the player had installed. **The build revision is a different
thing and must not be bumped to match**: it is what makes every existing cabin
rebuild itself, so it moves only when the cabin's geometry or fittings do.

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

**The 2026-09-20 torpedo pass** turned the weapon's visible half back on. It
had been killing in silence because `C.TorpedoFireChance` was 0 — and in this
engine the visible part of an explosion *is* the fire and the smoke. A
comment and a test were both holding that zero in place, and both were
accurate about the engine and wrong about the goal (*A guard is only as good
as the goal it was written from*). The fire now burns buildings, the torpedo
is drawn crossing the ground and detonates on arrival rather than on the
trigger, and server owners get `TrekShuttle.TorpedoFire` to keep the weapon
without the arson. Nine mutations checked, all caught, and **confirmed in game
the same day**: it is visible, it burns buildings down, and the blast size and
fire spread both needed no adjusting. The controller reticle is still not
built. `PHOTON_TORPEDOS.md` is now a working guide rather than a plan.

**Seen working in game** (2026-09-20, later): photon torpedoes with their fire
and their projectile, and the **mek'leth, lirpa and ushaan-tor** alongside the
bat'leth -- all four at the right size with icons that stay in their own hotbar
slots. The torpedo's blast size and fire spread both needed no adjusting.

**The 2026-09-20 EMH** is the last item on `ROADMAP.md`'s *ship systems* list
and the first system in this mod that reaches an **existing save**: the wall
station at 3,3 and the clear square at 2,4 were authored into the interior by
the refit, so `C.BuildRev` 22 is the whole migration and no fresh world is
needed. He is a world model standing on the deck, placed and removed by the
server the way the replicator and the warp core are; the panel is the helm's
LCARS a third time; his supplies are infinite and his power is the same
dilithium the replicator burns; and the cure for zombie infection -- the one
thing nothing else in the mod touches -- costs a whole crystal and twelve game
hours aboard, spent the moment it starts. `EMH.md` is the working guide, and
section 14 is the play-through.

Three things about it are worth carrying past this feature:

- **A vanilla call site proves reachability, never correctness.**
  `SetBitten(false)` is the obvious cure, vanilla's own admin health cheat
  calls it that way twice, and its bytecode clears the bite and then infects
  the limb regardless. A player would have paid a crystal, slept twelve hours
  and woken up infected on a bleeding arm, with the log silent.
- **A derived flag that latches needs clearing at both ends**, and the moodle
  is a third end that no packet carries.
- **Render it and look**, again. The Doctor came out of the importer facing
  north -- standing in the sick bay with his back to the whole cabin -- and
  his scanlines came out as wood grain, because an auto-unwrapped atlas has
  no horizontal. Both were invisible in the source and obvious in one picture.

Thirty-two mutations were run one pass at a time -- ten of the guards, nine
of the cure, four of the separation, four of the timer and the model and five
of the protocol -- and the first pass caught twenty-three. Of the nine that
survived, **three were real design faults and three were tests passing for
the wrong reason**; the rest were the harness only running one suite. All of
that is in `EMH.md`'s *What would have bitten you*, and the two general
lessons are the sections
*A vanilla call site proves reachability* and *Single player cannot test a fix
that both ends apply* above.

**Not yet seen in game**, in the order worth checking:

0. **The EMH**, built 2026-09-20 and not played at all. The only one on this
   list that needs **no fresh world**. `EMH.md`, *Not built, and still to
   settle in game*.
1. **Dilithium and the warp core**, built 2026-09-20 and not played at all.
   The ship's power is a crystal now, held in the mod's own model at 1,3 with
   *Load a crystal* and *Take a crystal* on its menu; twelve vanilla loot
   tables to find more in; a tricorder pass that plots them out to twenty
   tiles and reads the ground from the air; and no way to replicate one. **It
   needs a fresh world** -- both the ship's spares and the ones in the town
   are placed when the world is made. The route to check it is at the end of
   `REPLICATOR.md`.
2. **The replicator**, half-settled on 2026-09-20: it loads, the catalogue is
   4913 items in 78 categories, 19 patterns seed, and the machine places where
   it was authored. The first version could not be right-clicked at all, which
   is now a rule of its own above; the counter it leaned on is gone and the
   model has been scaled down since. Still open: the fixed menu, whether the
   machine earns its place at its new size, the panel under 4913 rows, and a
   pattern crossing between machines.
3. **The interior refit**: the shape, the three lockers, the five empty
   containers, the biobed as a bed -- and, in a save made before it, the
   migration. `INTERIOR_REFIT.md` section 7. **The television is off this
   list: it has been switched on and used repeatedly in game, and it plays
   tapes** (2026-09-23).
4. **The medical set**: the three items in the sick-bay locker, a dose that
   leaves a bite alone, the health panel at doctor level, the sensor sweep in
   front of a horde, and the lock override on a door and then on a padlock.
   `MEDICAL_SET.md`'s *Not built, and still to settle in game* is the list.
5. **The dedicated server**: the interior cell loads there, the server-built
   cabin reaches the client with its stock, water fills with the mains off.
6. **Two players**: one cabin, loot taken by one gone for the other, crew
   access, charges — and a shuttle in the air seen from the other machine,
   which is the last unproven thing about flight.
7. **The phaser firing** and staying charged on a server.

**The pattern worth carrying forward.** Six separate bugs in this mod have
had the same shape: a plausible engine call that fails silently, leaving a
thing that is present, drawn, and inert — an unopenable locker, a container
handed items that were never created, a tap topped up through an API it does
not have, a menu hook that never ran, a floor removed without its shadow, a
weapon model declared one module away from where the engine looks. Static
checks caught none of them, because the mod's logic was correct every time. What caught them was **reading the result back and logging
it**: `B.stockReport()` turned three sessions of guessing into one grep. When
you add something to the cabin, add the line that proves it arrived.

**The 2026-09-20 medical pass** built all four: the hypospray, the dermal
regenerator, the medical tricorder and the tricorder, with their icons, three
generated sounds, an LCARS contact plot and a server-side lock override. **None
of it has been seen in game.** `MEDICAL_SET.md` is the dev guide for it -- how
each instrument works, how to change one, the engine facts not to re-derive and
what will bite you, in the shape `PHOTON_TORPEDOS.md` uses -- and it carries
two corrections to what it used to claim: `ISHealthPanel` **is** an
`ISPanelJoypad`, so the controller question needed no work at all; and the
lock setters' own sync is skipped on a server, so the authority has to call
`obj:sync()` itself.

The expensive near-miss in that pass is worth repeating here, because no check
in this repository would have caught it: `BodyPart.RestoreToFullHealth()` is
the obvious way to mend a limb and it clears the **bite** as well. The
hypospray is specifically decided not to cure a bite -- that is the EMH's --
so the tidy version of the feature would have been silently better than
intended, and the next item on the roadmap silently pointless. See *A
convenience method is a bundle of writes somebody else chose*.

**The 2026-09-20 interior refit** cut the cabin from 6x9 to **4x6** --
fifty-four squares to twenty-four, against a hull that is fifteen. Three
Starfleet lockers (armoury, rations, sick bay) stocked with **the mod's own
items only**, five containers left empty on purpose because a player fills a
shuttle with vanilla loot within a week, a working television in place of the
viewscreen that was never a television, a wall panel and a clear square for
the EMH, the biobed as the ship's only bed, and the helm console prop deleted
for doing nothing. Revision 17. `INTERIOR_REFIT.md` is the working guide; four
new sections in this file came out of it. **None of it has been seen in game,
and the migration out of a 6x9 save is the part that most needs a real world
to prove.**

**The 2026-09-20 replicator** is the ship's first system rather than an item:
a lit alcove over the galley counter that makes anything in the game, gated by
a *pattern* the ship has scanned and an energy *reserve* that refills on the
world's clock. The catalogue is the engine's own item list rather than a
recipe file, so it covers vanilla, future patches and other people's mods with
no maintenance; the item is made on the server and the tray is counted after
every one. Revision 18. **First look in a game the same day**: it loads, the catalogue
comes out at 4913 items, the alcove places and hangs where it was authored to
-- and the right-click on it did nothing at all, because a click lands on the
floor square under the cursor and the model is drawn above its own. That is a
new rule above, and it is fixed. `REPLICATOR.md` is the working guide -- what happens when somebody uses it,
how to change each piece, the engine facts not to re-derive, and the seven
things to check the first time it is carried into a world.

Eight new sections of this file came out of it, plus a refinement to a ninth:
a table that is transmitted whole cannot hold a list that grows; a vanilla
call site under `AdminPanel/` is not a vanilla call site; a check against an
empty set is not a passing check; a branch a mutation cannot break may be
unreachable; a harness must record the distinctions the code makes; a dropped
world model picks its own angle; a string that gets upper-cased has to be
ASCII; a check that runs after a self-healing pass checks the healing; and the
simulation has to be as unkind as the engine, which has now cost seven holes
rather than three.

**The 2026-09-23 wardrobe** is `ROADMAP2.md` 1.4, and the roadmap's biggest
open question turned out not to exist. Of the 1,795 clothing items build 42
ships, 597 have no mesh at all and the rest share a small pool of rigs -- 7
ride `bob_boilersuit` -- so **a uniform is a 256x256 texture and not a rigging
job**. Six garments: a one-piece duty uniform on the boilersuit rig and a long
dress uniform on the judge's robe, which is the only skirted geometry in the
game carrying both a male and a female model. Three divisions each, both
bodies, the masks and ground models and blood locations all inherited from the
vanilla garment that already wears that geometry. Revision 24. `UNIFORMS.md`
is the working guide.

`tools/gen_uniform.py` writes the textures, the icons, the clothing XML and
the GUID table from one list, and the textures are painted from each rig's own
UVs in **world position** -- the EMH's lesson, applied before it could bite
again. Four new sections of this file came out of it: a garment is reached by
GUID and an unknown GUID is null; ask the asset which way round it is rather
than deriving it; one texture on two bodies has to mean the same thing on
both; and a mutation that does not apply proves nothing.

Sixteen mutations were run one at a time and all sixteen were caught -- but
only after the harness learned to assert that its own edit had applied, which
is how the one apparent MISS turned out to be a backslash in the harness
rather than a hole in a check.

**Seen working in game** (2026-09-23), the same day: the armoury carries all
six, they wear, and they draw. That was the one thing no static check could
reach -- whether the mod's own `fileGuidTable.xml` merged into the engine's
table -- and it is the whole chain in one observation, because every file can
be perfect and every uniform still draw nothing with nothing in the log.

Three art faults survived every check and were caught by *looking at it*: the
combadge sat on the hip, the texture had vanilla's breast pockets and zip
showing through borrowed luminance, and the collar was a black bib from
shoulder to shoulder. All three are in `UNIFORMS.md`; the first two are the
sections above. A female character, the replicator listing and two clients are
still unproven.

**The 2026-09-23 contact store** is `ROADMAP2.md` step 3, built against
synthetic contacts because that is what the roadmap asks for: the store, its
bounds, its map view and two-client publication can all be proven before a
probe exists to fill them.

`TREK_Probes.lua` already existed from an earlier session and **was required
by nothing** -- dead code that never loaded in the game, with most of its
config constants unreferenced. It is wired in now, and three faults came out
of writing the tests for it: a kind and a status were both unchecked strings,
and the history bound was applied only when a contact was *created* when the
thing it bounds is changed by `setStatus`, so the resolved list sat one over
its cap for the life of the save.

The map view is deliberately a **view**. Build 42 has a complete shared
annotation system and Lua is handed the drawing end and not the sharing end,
so contacts are the mod's own bounded store and the symbols are rebuilt from
it when the map opens and removed when it closes. `MAP_MARKERS.md` is the
research and `tests/test_multiplayer.py` has three new sections.

**The 2026-09-23 probes** are step 4, and they make the whole of step 3
visible: right-click aboard, *Long-range sensors*, *Launch probe (250 units)*.
One atomic authority-side transaction, a bearing the **server** picks, a
logical job advanced on the game-minute tick with its progress persisted, and
a report that is either an approximate dilithium fix or an honest nothing.
`PROBES.md` is the working guide.

The console is a submenu rather than a fitting: it would have cost one of
twenty-four deck squares and a BuildingEd change, and *Shuttlecraft ->
Long-range sensors* reaches the player in the same two clicks the helm does.
The launch option carries its own cost, for the reason the warp core's options
carry their spare count.

Two harness gaps came out of it, and both are the shape this file keeps
meeting: `pz_sim`'s `addSubMenu` was a **no-op**, so every option one level
down was invisible and the whole sensors menu could have been empty; and the
runtime never loaded `shared/Definitions`, where map symbols register, so the
map tests would have passed against symbols the game would never have had.

Ten mutations, all caught -- one only after the "impossible" refund branch in
the launch handler was made to log a WARN. Until then it refused with the same
reason the guard above it would have given, and nothing could tell the two
apart.

**The 2026-09-23 sensor console** is what the probes became after ten minutes
of play. Five things came back from it and all five are in:

* a **panel** rather than a menu -- the mod's fourth LCARS console, with a
  progress bar, because a probe that is "away" for an hour of game time with
  nothing moving reads as broken;
* **probes as stock**: energy fabricates one, a launch spends one, eight in
  the rack. "Three probes aboard" is a state a player can plan around;
  "830 units of reserve" is arithmetic they have to do first;
* **real crystals**. A contact is a record until a player loads its ground,
  and then the server puts an actual `TrekDilithium` on the first square that
  will hold one -- deferred placement, the `s.ghosts` pattern run backwards;
* the **map uncovered** around a contact, with `setKnownInSquares`, which is
  precisely what reading a paper map does
  (`shared/TimedActions/ISReadABook.lua:318` -- ordinary shared code);
* and the `%` bug: a literal per-cent sign beside a `%1` came out as
  "Probe in flight -- 16$s%". No other translation in this mod has one, which
  was the tell.

Two mutation escapes, and they wanted opposite fixes. A proximity pre-check
before placing a crystal could not be observed at all -- `chunkLoaded` already
said the same thing -- so it was **deleted**. And the whole-area load check
*was* load-bearing and untested, so the test that reaches the expire path was
**written**: a contact with genuinely nowhere to put a crystal retires itself,
and one whose ground is merely not loaded must never. Getting those two the
same way round destroys a contact the moment somebody walks past the edge of
it.

**And the first thing play found** was that adding a map symbol *category*
crashes the world map. Vanilla's palette lays a category out eight buttons to
a row and then reads `joypadButtonsY[floor(rows / 2)]`; a category with one
row indexes `[0]`, which is nil, and `#nil` throws inside vanilla with an
error naming neither the mod nor the symbol. **Nine symbols** is the minimum a
category can be laid out at, and vanilla's own three all hold twenty-eight or
more. The mod's two join `Locations`, and `tests/test_assets.py` now refuses
any category vanilla does not already have enough symbols in.

It is the same shape as *A vanilla call site proves reachability, never
correctness*, one step further out: the call was right, the arguments were
right, and the **shape of the data** was outside what vanilla's own UI can
cope with.

**And the second thing play found** was not a bug at all: a probe came back
empty, which is a 35% outcome working exactly as designed, and it was reported
as broken -- correctly, because the only trace of it was a line in
`console.txt`. From inside the game an honest empty result and a feature that
did nothing are the same thing. The fix is three lines of feedback and one
design change: the crew are told when a probe lands either way, the verdict
stays on the console afterwards, and **the first probe of a save always finds
something**.

The general shape is worth more than the fix: **a correct refusal that nobody
is shown is indistinguishable from a broken feature**, and this file already
says the same thing about `deny()` reasons and about `TREK_Uniform()`. An
outcome the design calls valid still has to be delivered to the player, not
merely recorded.

**The 2026-09-23 two-player flight** is the first time anything in this mod has
been played by two real people, and it cost one bug and one design decision.

The bug: *"in hover it snaps us back basically forever, but if I go backwards
it seems to work"*. `keepLevel` read `getAngleX()`/`getAngleZ()` as pitch and
roll -- they are two corners of an Euler decomposition, and both read **180**
for a ship that is dead level but turned more than a quarter turn from the
heading she spawned at -- and then called `flipUpright()`, which is
`setAngleAxis(**0**, Y)`: the identity, heading and all, applied by teleporting
the physics body. Ten times a second. Reverse worked because reversing never
leaves the safe half of the compass. It has been there since the day flight was
built, and every test passed because `pz_sim.lua` stored the three angles
instead of decomposing a rotation -- hole nine in *The simulation has to be as
unkind as the engine*. Two new sections of this file came out of it: *A getter
named for an axis may be one corner of a decomposition* and *An offer the ship
cannot keep is worse than a smaller offer*.

The decision: **flight is a binary**. Four altitudes with *Climb* and *Dive*
went to one, `C.FlightLevel = 1`, and `setAltitude` was deleted from both ends
rather than left as a polite ceiling -- only the ground and level 1 ever
behaved in play, and level 1 is not arbitrary: the engine accepts a height with
a floor at that level *or the one below*, and one below level 1 is the ground.
With it: the hatch stays shut while she hovers, so the transporter is the only
way out of her, and **when the last of the crew beams down she goes back up**
rather than dropping five tonnes of shuttle onto whatever is underneath.
`landed = false` is the state a recall already leaves her in, so calling her
down again needed no new code. `PILOTING.md` is rewritten around all of it.

Three mutations, all caught: the old `flipUpright` levelling (the heading test
fails at 135, 180 and -135 degrees and passes everywhere else, which is the
reported symptom exactly), `crewAboard`'s seat test back to `~= nil` (which is
how it shipped -- `U.try` hands back the value, so a successful call answering
*false* counted as aboard and only death ever ended a flight), and
`S.endFlight` without its `toOrbit`.

**The same evening's second report** was four symptoms and one line. The
watchdog that notices nobody is aboard a hovering shuttle lived inside
`serviceVehicle`'s `if found then` block, and `found` is nil exactly when
nobody is standing near her -- which is exactly the case it exists for. A crew
who beamed down and walked away left her flying for ever: hatch refused, recall
refused, and a call-down that spawned her on the ground and was lifted straight
back into hover by every client because `flying` was still set. It runs
unconditionally now; `S.recall` sends an empty hovering ship back up; `S.land`
refuses a call-down from under her pilot by name and otherwise ends the flight
before it lands her; and `Core.enter` says why instead of returning false in
silence.

That session also found a door with no handle on the inside: going aft to the
cabin in flight had no return leg, so a pilot who stepped through could never
fly her again. *Forward to the cockpit* is the aboard menu's answer, arriving
on the ground beneath her and using vanilla's own `vehicle:enter(seat,
character)`. Two more sections of this file came out of the pair. Six
mutations, all caught -- one of them only after the "unreachable" branch it
covered was given a reachable path (a crewman calling her down while somebody
else flies her), which is *A branch a mutation cannot break may be
unreachable* answered the other way round: the branch was real, the caller
was missing.

**Still unproven**, and only the game can say: whether the other machine draws
her in the air, and whether ten checks of `FlightPilotGrace` plus thirty of
`FlightBoardingChecks` is enough room for a real beam on a real connection.

**The 2026-09-24 downed ensign** is `ROADMAP2.md` 1.7, built ahead of 1.6's
cold start, whose only hook into it is one line (`M.hearing()`). A distress
call once the ship has been boarded and has dilithium; Accept and Decline on
the sensor console; a `downedPersonnel` contact with a three-day clock; a
figure placed when a player loads its ground; the server's beacon drawing in
the dead already there; the client's chirp; a blue cross on the tricorder;
and a right-click rescue that pays out three patterns and a small supply
exactly once. `ENSIGN.md` is the working guide.

The figure is the answer to "can it be animated": no -- only characters play
animations, and the characters a mod can put in the world are either not
networked or zombies -- but the game's own files can be *baked*: the vanilla
body, the mod's uniform, one frame of the game's own pain animation
(*A pose can be baked out of the game's own files*, above).

Its first two-client test found a live bug that had nothing to do with it: on
a server, a player standing in the cabin had no position fix, so probes
launched aboard would have been refused (*Player mod data a client writes is
not the server's*). Seventeen mutations, one pass at a time, all caught --
after one test that passed because the ground it stood on was unloaded was
moved to ground that was not.

**Played end to end in single player the same day**: call, accept, mark,
tricorder, rescue, three patterns learned. `ENSIGN.md` section 9 has what is
still open, chiefly two clients.

**The 2026-09-24 PADD** is `ROADMAP2.md` 1.8: a tablet that holds digital
copies of books, without limit, read five times faster than paper, copied
between PADDs, and lost with the PADD. It is the mod's **first timed
action**, and the first thing checked was whether a mod's own action runs
its server half in multiplayer -- the bytecode says it is rebuilt there by
class name and by `new`'s parameter names (*A timed action is rebuilt on the
server...*, above). Reading is its own action, applying `ISReadABook`'s
effects to a book rebuilt in no container, because a real book in the
reader's hands would be a duplication exploit. Seventeen mutations caught.
Build revision 28, for the armoury's two PADDs. `PADD.md`. Not yet played.

**Next up** is `ROADMAP.md`'s step 7: publishing -- or `ROADMAP2.md` 1.6, the
cold start, if it is to ship with the ensign. Everything else on the roadmap
is built; what is left is playing it. Four systems have never been in a game at
all, and the two-player session has been pinned for long enough that it is now
the largest single piece of unproven work in the project.

Known limits are listed at the bottom of `README.md`.

---

## Layout

```
design/buildinged/TrekShuttle_Interior.tbx                     the interior (4x6), in the map editor
TrekShuttle/42/media/sandbox-options.txt                       server-owner settings
TrekShuttle/42/media/lua/shared/TREK/TREK_Config.lua           all constants — start here
TrekShuttle/42/media/lua/shared/TREK/TREK_Util.lua             safe wrappers, state schema, geometry, stocking
TrekShuttle/42/media/lua/shared/TREK/TREK_Net.lua              client -> server commands, replies
TrekShuttle/42/media/lua/shared/TREK/TREK_Power.lua            each fitting's own cell, and the ship's dilithium reserve
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
TrekShuttle/42/media/lua/shared/TREK/TREK_Medical.lua          treatment, doses, the cure, what counts as a lock
TrekShuttle/42/media/lua/shared/TREK/TREK_EMH.lua              the Doctor's rules, shared so the panel and the ship agree
TrekShuttle/42/media/lua/shared/TREK/TREK_Replicator.lua       the item catalogue, patterns, what a thing costs
TrekShuttle/42/media/lua/server/Items/TrekDilithium.lua        where crystals spawn in the world
TrekShuttle/42/media/lua/client/TREK/TREK_ReplicatorUI.lua     the replicator panel and its menus
TrekShuttle/42/media/lua/client/TREK/TREK_WarpCore.lua         the warp core's menu: load a crystal, take one back
TrekShuttle/42/media/lua/client/TREK/TREK_MedKit.lua           the medical set: menus, panels, the sweep
TrekShuttle/42/media/lua/client/TREK/TREK_EMHUI.lua            the Doctor: his menu, his panel, his light, consent
TrekShuttle/42/media/lua/client/TREK/TREK_Menu.lua             right-click menus, crew
TrekShuttle/42/media/lua/server/TREK/TREK_Missions.lua         distress calls and the downed ensign: the authority
TrekShuttle/42/media/lua/client/TREK/TREK_EnsignUI.lua         the ensign's right-click menu, the chirp, the notes
TrekShuttle/42/media/lua/shared/TREK/TREK_Padd.lua             the PADD's library: books, entries, reading arithmetic
TrekShuttle/42/media/lua/shared/TREK/TREK_PaddActions.lua      the PADD's timed actions (global, shared: the server rebuilds them by name)
TrekShuttle/42/media/lua/client/TREK/TREK_PaddUI.lua           the PADD's inventory menus
TrekShuttle/42/media/clothing/clothingItems/*.xml              the six uniforms: vanilla rigs, our textures (generated)
TrekShuttle/42/media/fileGuidTable.xml                         the GUID each garment is reached by (generated)
TrekShuttle/42/media/textures/clothes/trek/*.png               the uniform textures (generated)
TrekShuttle/42/media/lua/shared/TREK/TREK_Probes.lua           the contact store: bounded, server-owned, its own mod-data key
TrekShuttle/42/media/lua/client/TREK/TREK_MapContacts.lua      contacts drawn on the world map, rebuilt from the store
TrekShuttle/42/media/lua/shared/Definitions/TrekMapSymbols.lua the map symbol registration (generated)
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
