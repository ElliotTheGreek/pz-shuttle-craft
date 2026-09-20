# The replicator

**Built, revision 20. Carried into a game on 2026-09-20, twice: it loads and
it places, and the two looks cost one real bug and a rebuilt fixture. The
power behind it -- dilithium -- is built and tested and has not been played
yet.**

A machine standing at the aft end of the galley that makes any item in
Project Zomboid, and **owns its square**: no counter under it, and no
container borrowed from a piece of furniture. What it makes goes into your
hands.
Two limits stand between the player and that, and they answer two different
questions:

- a **pattern** decides *what*. The ship can make a thing once it has scanned
  one, which turns looting from "find supplies" into "find the first one".
  Scanning is free and gives the item straight back, and the ship knows its
  own Starfleet gear from the day the world is made;
- **energy** decides *how much*. Every replication spends from a reserve, and
  **nothing refills that reserve for free**: it is a dilithium crystal burning
  in a chamber amidships, the ship swaps in a spare when one is spent, and a
  crystal is a thing you can only find out in the world. The machine that
  removes the need to loot has a leash that can only be found by looting.

A server owner who wants neither, or none of it at all, has one sandbox
option with three values.

This file is the working guide: what happens when somebody uses it, where
each piece lives, how to change one, the engine facts not to re-derive, and
what will bite you. `DEV_GUIDE.md`'s *Rules that exist because they were
broken* applies to every line of it, and `MULTIPLAYER.md` is the client and
server split every feature here obeys.

---

## What happens when the player uses one

```
client   stand at the machine (0,5), right-click it
         TREK_ReplicatorUI.fillMenu -- OnPreFillWorldObjectContextMenu, keyed
         to the square, greyed with a reason when it is off or you are too far

         TREKReplicatorWindow: the catalogue, filtered as you type, the
         reserve across the top, a quantity of 1, 5 or 10
             "Materialise"  -> Core.send("replicate",    { id, count })
             "Scan"         -> Core.send("scanCarried",  {})
         and, from an item's own inventory menu,
             "Store a pattern"  -> Core.send("storePattern", { id })

server   Net.onServer("replicate")           TREK_Server.lua
           alive, and Ship.canUse            the ship's own access rule
           the sandbox is not Off
           Rep.inReachOf(player)             measured HERE, not sent
           Rep.row(id)                       the real catalogue, never a
                                             string handed to instanceItem
           Rep.isQuantity(count)             one of the three the panel offers
           Rep.knows(id)                     unless the sandbox says otherwise
           the ship's cooldown
           Power.afford(cost)                and if the reserve is short, this
                                             is where a spare crystal is taken
                                             out of the chamber and burned --
                                             or the whole thing refused,
                                             because there is none
           -> materialise(player, id, count) instanceItem, AddItem into the
                                             asking player's own inventory,
                                             sendAddItemToContainer, and the
                                             inventory counted after each one
           -> spend for what LANDED, commit
           Net.toClient("replicated", { made, asked, cost, energy })

client   a note saying what happened, the materialisation sound, and the
         panel redraws from the ship state the server just published
```

The pattern set is published separately, and only when it changes.

---

## Where everything lives

| | |
|---|---|
| `shared/TREK/TREK_Replicator.lua` | the catalogue, the blocklist, the patterns, what a thing costs, where the machine stands |
| `shared/TREK/TREK_Power.lua` | **the ship's reserve and the crystal it burns**, below the line that separates it from the device cells -- which are a different thing entirely |
| `server/TREK/TREK_Server.lua` | the three handlers, the run, `S.replicatorReport()` |
| `server/TREK/TREK_Build.lua` | `furnishReplicator()`, which stands the machine on its square once, and `removeLegacyBerth()`, which takes out the counter it used to lean on |
| `client/TREK/TREK_ReplicatorUI.lua` | the panel, both menus, the replies |
| `shared/TREK/TREK_Config.lua` | every number, and the sandbox values |
| `TREK_Config.lua` | `C.ReplicatorSpot` -- 0,5, and **no layout entry at all**: the machine owns the square |
| `server/Items/TrekDilithium.lua` | where crystals spawn in the world, and nothing else |
| `shared/TREK/TREK_InteriorLayout.lua` | the dilithium chamber at 1,3: a tool cabinet, tagged, stocked when the ship is built |
| `client/TREK/TREK_MedKit.lua` | the tricorder's mineral pass, which is how a player finds one |
| `tools/gen_replicator.py` | the machine's mesh and texture, the sound, and the renders |
| `tools/gen_dilithium.py` | the crystal's icon |
| `media/scripts/trekshuttle.txt` | `item TrekReplicator`, `model TrekReplicatorModel`, `sound TREK_Replicate`, `item TrekDilithium` |

---

## Changing it

### What a replication costs

`C.ReplicatorBaseCost` (4) plus `C.ReplicatorWeightCost` (10) per kilogram,
rounded, floored at 1 and capped by `C.ReplicatorMaxCost` (150). So a bandage
is 5, a tin of beans 12, a hammer 24, a shotgun 44, and a 60 kg generator is
the cap rather than the 604 the formula would otherwise ask for.

Weight because it is the one number every item in the game has, and because
it is roughly what the thing *is*. There is no per-item table and there
should not be one: the catalogue includes other people's mods, so any table
would be a list of the items somebody thought of.

### The reserve, and the crystal that fills it

`TREK_Power.lua`, below the line. One number in the ship state -- `s.power`,
0..`C.PowerMax` -- spent by the replicator and, when it is built, by the EMH.
It is the *ship's* power rather than the replicator's, which is why it does
not live in `TREK_Replicator.lua` and why `R.energy()` is one line that asks
`TREK.Power.reserve()`.

**Nothing refills it for free.** It was twenty units every ten game minutes
for one revision, which made the replicator a machine you *waited at* rather
than one you fuelled -- a cooldown wearing a hat, which is the exact thing the
cost model was chosen to avoid. The reserve is now one crystal, burning:

| | |
|---|---|
| `C.DilithiumCharge` | **5000**, and `C.PowerMax` is the same number: the reserve *is* one crystal, so the most it can hold is one crystal |
| `C.DilithiumIssue` | **3** spares in the chamber on a new ship |
| `C.DilithiumItem` | `TrekShuttle.TrekDilithium`; `C.DilithiumType` is the bare `TrekDilithium`, for the engine's recursive search |
| `C.DilithiumTag` | `dilithium` -- the layout tag on the chamber, which is how `P.chamberSpot()` finds it without a second constant to keep in step |
| `C.CrystalScanRadius` | **20** tiles, against the lifesign sweep's 40 |

Five thousand is **a thousand bandages, or two hundred hammers**, and that is
the feel of the whole system: the interesting part is the trip out to find
one, not rationing the last forty units. A crystal that ran out in an
afternoon would turn every replication into a sum.

`P.afford(cost)` is the only thing that should ever burn one. It answers true
when the reserve covers the cost; when it does not, and only on the authority,
it takes a spare out of the chamber, sets the reserve to a full crystal and
answers again. Two things it will not do: burn a crystal for a cost a *fresh*
crystal could not cover either -- nothing costs that much today, the dearest
replication being 1500, but both numbers are tunable and eating a player's
crystal and then refusing them is the worst failure available to this code --
and burn anything at all on a client.

The swap **sets** the reserve rather than adding to it: whatever was left in
the old crystal is lost. That is why it only happens when the reserve
genuinely cannot cover the request.

`P.burnCrystal()` reads the container back after the removal. A `Remove` that
did nothing would burn the same crystal for ever, which is an infinite power
supply and the precise opposite of the point.

### One refusal, not two

`IGUI_TREK_RepNoCrystal`, with the numbers in it. There was a second one --
"not enough in the reserve" -- for a low reserve with spares still aboard, and
**it could never fire**: a fresh crystal is 5000 and the dearest thing in the
game is 1500, so whenever a spare exists the swap covers the cost. It was
deleted rather than kept for symmetry. If the numbers are ever tuned so one
request can cost more than a crystal holds, that refusal comes back *with a
test*, and `P.afford`'s ceiling check is already there waiting for it.

The panel follows the same rule: the Materialise button is live when the
reserve covers the cost **or there is a spare in the chamber**, because the
ship loads one by itself. Greying it on a low reserve would refuse something
that would have worked.

### Where the crystals come from

`server/Items/TrekDilithium.lua`, and nothing else in this mod touches the
world's loot. Twelve vanilla tables weighted 0.2 to 0.6 on vanilla's own scale
(a diamond in `JewelryGems` is 1): a jeweller's gem case, a pawn shop, a few
electrical shelves, a metal shop, tool crates, a garage. That list is doing
the same job the tricorder does -- telling a player where to go -- so it is
worth keeping it somewhere a person would guess.

The file deliberately does not `require` any of the mod's own code: it runs at
world generation, and a load-order dependency there would be an empty world
with nothing said about it. It reads its own result back and logs how many
tables it found, because a vanilla table renamed in a patch would take the
crystal out of the world in silence. `tests/test_assets.py` checks all twelve
names against the **installed** game -- the same check, happening before a
world is generated rather than after.

### The chamber

A tool cabinet at 1,3 in `TREK_InteriorLayout.lua`, tagged `dilithium`, with
`special = "dilithium"` so `TREK_Build.lua` stocks it with `C.DilithiumIssue`
crystals when the ship is built. **The container is the truth**: there is no
count in the ship state to drift out of step with it, and the server reads and
writes the same container the player opens.

A crystal **cannot be replicated** (`C.ReplicatorBlocked`), which is the point
of the arrangement rather than a balance decision.

### Finding one

The tricorder's sweep has a second pass. It walks the squares within
`C.CrystalScanRadius`, counts crystals lying on the ground *and* inside any
container on the square -- which is where every crystal in the world actually
starts -- and plots each trace as a ring with a bright middle, against **its
own radius** rather than the lifesign one. A trace plotted against the longer
radius reads as much nearer than it is, on the one instrument a player walks
by.

The readout says *Dilithium* and a number whether or not anything was found:
"none in range" is the answer a prospector needs, and a line that only appears
on a hit is one a player cannot learn to look for.

### What the ship already knows

Every item declared in `module TrekShuttle`, seeded by `R.seedDefaults()` on
each authority start -- not once, so an item added to the mod later is a
pattern in an existing save with no migration. It publishes only when
something was new.

### The blocklist

`C.ReplicatorBlocked`. Three ids today, and all three are items this mod
declares for its own purposes: the torpedo specification (a warhead nobody
holds, with no icon), the hull, and the deleted helm console. **The engine's
own filter does not catch any of them** -- they are not obsolete, not hidden
and not in `Moveables` -- which is precisely why the list exists.

Add to it rather than to a filter: a server owner reading the config should
be able to see what the ship refuses to make.

### The quantities

`C.ReplicatorQuantities` = `{ 1, 5, 10 }`. The panel cycles them and **the
server checks the number against the same list**, because it arrives from a
client: without that check the command is an item printer.

### Where it is in the ship

`C.ReplicatorSpot` -- 0,5, the aft end of the galley. A constant rather than a
tag in the layout, because **there is no fitting on that square**:
`tests/test_layout.py` fails if anything is authored onto it, if it falls
outside the hull or onto the pad, or if there is no square beside it to work
it from.

It was a steel counter for two revisions, with the model hanging over it and
replicated items going into the counter's own container. `B.refitCabin` takes
that counter out of a save that still has one -- it is tagged, and
`U.clearSquare` keeps tagged things by policy, so nothing else ever would --
and spills what was in it onto the pad.

### The machine

`python tools/gen_replicator.py TrekShuttle/42` writes the mesh, the texture,
the sound and two renders into `design/art/replicator/`. **Authored from the
deck up**: 1.62 tall, one tile, a kick plinth, a lit niche at chest height, a
shelf under the niche and a capped top with a readout.

It was a wall alcove hanging over the counter for two revisions, and that was
wrong in both of the ways it could be. It *looked* wrong -- too tall, too
dark, and floating over a piece of furniture doing its work for it. And a
model drawn above its own square **cannot be right-clicked at all**, because a
click resolves to the floor square under the cursor: the first version could
be seen and not used. Standing it on the deck fixes the gesture as well as the
look, which is usually the sign that the geometry was the problem rather than
the code.

### The panel

Built from the helm's LCARS parts (`H.pill`, `TREKLcarsButton`, `H.P`), so
the two consoles look like the same ship. `tests/test_helm.py` draws it
against a 122-row catalogue with a name too long for its column.

**The list is a two-level tree**: the categories the game itself puts items
in, then the items in one, with Back out of it. It was a button that cycled
one category per press, which against the seventy-eight a real game has is not
a control at all. Each category row says how many of its items the ship has
patterns for -- the number a player is actually looking for -- and **a toggle
narrows the whole panel to those**, categories included: one the ship has no
pattern in is not worth walking into, so it is not offered.

A search is a view of the *whole* catalogue and steps out of whatever category
you were in. Searching inside one folder while the box says otherwise is how a
player concludes an item is not in the game.

---

## The rules it obeys

| | |
|---|---|
| The item is created | **Server**, on a validated `replicate` |
| Who may use it | **Server** -- alive, the ship's `canUse`, standing at the machine |
| The pattern set | **Server**, its own mod data key, shared by the crew |
| The reserve | **Server**, ship state, one number. A client that has not been told yet reads it as *full*, so a panel opened before the first sync does not grey its own button |
| The crystals | **Server**, and they are items in a container rather than a number anywhere |
| The catalogue | **Both**, built per process from the engine's own list |
| The panel, the search, the list | **Client**, presentation only |

- **A client is a request, never a fact.** The id is looked up in the real
  catalogue, the quantity is matched against the list the panel offers, the
  range is measured on the server's own copy of where the player is standing,
  and the inventory a scan reads is the server's copy of it.
- **What is made is counted.** The inventory is measured before and after
  every single item, because `instanceItem` answers nil for an obsolete item
  that slipped the filter and a container at capacity drops what it is handed
  -- and from the server's side both look exactly like success.
- **The player is charged for what landed**, not for what they asked for.
- **An absent sandbox option means the feature as designed**, and here that is
  the *restrictive* reading. This is the opposite way round from
  `C.TorpedoFire` and both are deliberate.

---

## Engine facts, established

With `tools/pzapi.py` (exists, public) and a grep of vanilla Lua (may I call
it). Do not re-derive these.

| Fact | Where |
|---|---|
| `getAllItems()` is a `LuaManager$GlobalObject` static returning `ArrayList<Item>` | `shared/Foraging/forageSystem.lua:679` |
| `getScriptManager():getAllItems()` is the same list | `client/ISUI/ISLiteratureUI.lua:363` |
| **The filter for a usable item is `not item:getObsolete() and not item:isHidden()`** | `ISItemsListViewer.lua:53`, and `forageSystem.lua:680` for a non-admin one |
| Vanilla's own item viewer skips the **`Moveables`** module | `ISItemsListViewer.lua:71` |
| An **obsolete item is still in the scripts and returns nil from `instanceItem`** | `DEV_GUIDE.md`, *Changing what is in a container* |
| `Item.getFullName / getDisplayName / getDisplayCategory / getModuleName / getActualWeight / getNormalTexture / getObsolete / isHidden` are all public | `pzapi.py` |
| `getActualWeight()` is the weight of a **script** item, and vanilla calls it on one | `ISWorldObjectContextMenu.lua:2243` |
| `getScriptManager():FindItem(id)` looks one up by full type | `ISInventoryPaneContextMenu.lua:3086` |
| `inv:getAllEvalRecurse(function() return true end)` is everything a player carries, sub-containers included | `ISInventoryPaneContextMenu.lua:1355` |
| `ISTextEntryBox:new("", x, y, w, h)` with `.onTextChange` assigned on the instance | `ISChat.lua:162,171` |
| `instanceItem(id)` works on the server and is the only creation path this mod uses | `DEV_GUIDE.md`, *The jar is not the API* |
| An item added to a container already in the world reaches clients with `sendAddItemToContainer` | `MULTIPLAYER.md` |
| **A server may put an item in a player's inventory on a validated command**: `player:getInventory():AddItem(item)` then `sendAddItemToContainer(player:getInventory(), item)`. This is the engine's own idiom, not an invention -- vanilla does it a dozen times in one file | `server/ClientCommands.lua:187,206,651,699,718,914,1211` |
| **A right-click resolves to the floor square under the cursor**, so a model drawn above its own square cannot be clicked | seen in game, 2026-09-20; `DEV_GUIDE.md` |
| `container:getAllTypeRecurse(type)` compares the **bare** type, which is not namespaced -- so anything counting mod items filters the results on the full id as well | the phaser's sweep, the medical set's `carried`, and `P.crystals` |
| A distribution is added by appending an id and a weight to `ProceduralDistributions.list[name].items`, from `Events.OnPreDistributionMerge` | `server/Items/ProceduralDistributions.lua`, and every loot mod on the Workshop |
| Vanilla's procedural tables are indented with **tabs**, one level, inside `ProceduralDistributions.list` | the installed `ProceduralDistributions.lua` |
| A tile's container comes from its sprite properties -- `location_business_machinery_01_33` is a Tool Cabinet of capacity 20 | `tools/import_tbx_layout.py` output |
| `square:getWorldObjects()` is what is lying on the ground; each answers `getItem()` | the tricorder's mineral pass |

### The call site that does not count

`ISItemsListViewer.lua` is the obvious place to cite for `getAllItems()`, and
it lives in **`client/ISUI/AdminPanel/`**. By this project's own rules that is
not evidence: an admin-only file proves a method works for an admin, which is
the `setGodMod` shape all over again. The filter is quoted from it because it
is the clearest statement of the rule, but the two call sites that make
`getAllItems()` safe to use are the foraging system and the literature UI.

---

## Testing

```sh
python tests/test_multiplayer.py    # replicator(), replicator_multiplayer(),
                                    # the crystal swap and the crystal sweep
python tests/test_helm.py           # the panel, and the tricorder's plot
python tests/test_layout.py         # the machine's square, and that it is clear
python tests/test_assets.py         # the model, the sound, the icon, the
                                    # twelve loot tables, every string
```

`replicator()` plays it the way a player does: it right-clicks the berth,
opens the panel from the menu option, types in the search box and presses the
buttons. Driving the server handlers directly would pass against a build
whose Materialise button was wired to nothing, which is exactly how the
torpedoes once shipped unfireable.

**Twenty-one more mutations were run for the dilithium work, and the first
pass caught eleven of twenty.** Every one of the nine misses was a hole in the
tests rather than a mutation not worth catching, and four of them were the
expensive kind -- a check that passed for a reason that had nothing to do with
what it claimed:

- **the blocklist check was vacuous.** It asserted the crystal is not in the
  catalogue, and the crystal was not in the *simulation's* catalogue either,
  so deleting the blocklist entry changed nothing. `pz_sim.lua` now declares
  the three items the replicator must refuse, for exactly that reason;
- **the chamber count was tested against the test's own helper**, which
  re-implemented the filter it was meant to be checking. It asks
  `TREK.Power.crystals()` now, and the impostor it puts in the chamber is
  another mod's `TrekDilithium` -- a wrench proves nothing, because the
  engine's bare-type search never returns one;
- **the harness could not tell an outline from a filled rect.** Both were
  recorded as `rect`, so the tricorder's crystal rings were invisible to the
  test: a plot that drew no traces at all passed. They are recorded apart now,
  and the trace at the edge of the mineral radius has to land on the edge of
  the plot -- which is what catches a trace plotted against the wrong radius;
- **the crystal sweep had no test at all.** The panel test injects a result
  and draws it; nothing walked the world. `replicator()` now drops a crystal
  on the floor, leaves the chamber stocked, puts a third well out of range,
  and sweeps.

The check on the loot tables was mutated too, and found its own bug first:
the pattern reading vanilla's file matched nothing, so all twelve perfectly
good table names were reported missing. Both sides of that comparison have a
sanity check now, which is the general form -- *a comparison against an empty
set is not a passing test, it is a broken one*.

Before that, **nineteen mutations were checked against the replicator itself
and all nineteen caught** -- and three of those found tests that were passing
for the wrong reason:

- the quantity check was "proved" by the reserve, because 999 hammers cost
  more than the ship has. It asserts the *refusal reason* now;
- the sandbox `Off` check ran with a full tray, which refused by itself (the
  tray is gone now, and the check asserts the refusal's reason instead);
- the regen ceiling could not be broken by the mutation at all, because two
  separate guards clamp it. The test sets the reserve five short of full now,
  so the clamp is the only thing standing between it and overshooting.

Eight more mutations were run against the panel test, and one of those found
the same class of hole: the quantity button's wrap could be deleted without
failing anything, because an index that runs off the end makes `quantity()`
fall back to 1 and the first lap looks identical. It walks the cycle twice
now.

---

## What will bite you

- **Obsolete items.** Skip the filter and the catalogue fills with plausible
  entries that make nothing, silently. Said twice on purpose.
- **A container at capacity is silent**, and so is an item that will not
  instance. Count what arrived; never trust the number you asked for.
- **`Ship.commit()` transmits the whole ship table.** That is why the patterns
  are not in it. Anything else that grows without bound belongs in its own mod
  data key too.
- **Other people's items.** The catalogue holds ids this mod has never seen,
  with names it cannot predict and icons that may be missing. Nothing in the
  panel may assume `getNormalTexture()` answered.
- **`U.batch`, not `U.try`,** for anything that loops over the catalogue. A
  wrong method name over two thousand items is two thousand Java stack traces
  and a game that looks crashed.
- **The panel's first open builds the catalogue.** A few thousand items, once
  per process. If that is ever felt as a hitch, build it at load instead --
  but measure before believing it.
- **A missing reserve reads as full, on purpose.** `P.reserve()` answers
  `C.PowerMax` when the ship state has no number, because a client's copy is
  whatever the server last sent and before the first packet there is nothing
  at all. Reading that as empty would grey the button on a machine that has
  simply not been told yet. It also means *a bug that loses the number looks
  like a full tank*, which is the trade.
- **The bare type is not namespaced.** `getAllTypeRecurse("TrekDilithium")`
  will happily hand you another mod's crystal. Filter on the full id, every
  time -- the phaser and the medical set do the same.
- **A new fitting is scenery in the simulation until `pz_sim.lua` is told.**
  Its container comes from a list of substrings in the sprite name, and the
  chamber's `..._machinery_...` matched none of them: the cabinet was placed,
  never stocked, and the whole power system read zero crystals in eight
  different checks.
- **The alcove is a world item**, and world items are saved and deliberately
  preserved by `U.clearSquare`. Anything that places one must look first or it
  stands a second one at every rebuild.

---

## Not built, and still to settle in game

**Settled in a game on 2026-09-20**, over two looks:

- it loads, and the catalogue is **4913 items in 78 categories**, with no WARN
  anywhere and no pause worth the name;
- **19 patterns** seed on world load -- the ship's own gear;
- the model places and is drawn exactly where its vertices put it, which is
  the half of a world model that cannot be checked outside the game;
- **it could not be right-clicked at all.** A click resolves to the floor
  square under the cursor, and the model was hanging over the counter, so the
  menu -- keyed to the machine's square -- was never offered. `DEV_GUIDE.md`
  has it under *A right-click lands on the floor, not on the picture*;
- and the fixture was wrong: a dark slab floating over a steel counter that
  was doing its work for it. It is a whole machine now, standing on the deck,
  owning its square, handing what it makes straight to you.

Still to settle, in the order worth checking:

1. **The way in.** Standing beside it, right-click the machine: the option
   should read *Use the replicator*. From across the cabin it should be there
   and greyed, telling you to walk over.
2. **Whether it looks like it belongs**, now that it is a full-height unit in
   the galley row rather than a box on a bench.
3. **The tree under 78 categories.** Open one, come back, and try the
   known-only toggle -- the root should then list only categories the ship has
   patterns in.
4. **The panel under 4913 rows.** Typing should stay responsive; the filter
   walks a precomputed array, but that is reasoning until somebody types.
5. **The chamber.** A **fresh world** is needed: both the ship's three spare
   crystals and the crystals out in the town are placed when the world is
   made. Right-click the cabinet at 1,3 -- second row, port side, next to the
   lockers -- and three Dilithium Crystals should be in it.
6. **The swap.** The reserve is 5000 and a hammer is 24, so emptying it by
   hand is not a test anybody wants to play. Make a run of the dearest thing
   the tree offers at a quantity of 10 and watch the reserve fall by 1500 a
   press; when it can no longer cover one, the next press should still work
   and the chamber should be one crystal lighter. When the chamber is empty
   *and* the reserve is spent, the refusal should name the dilithium and give
   both numbers.
7. **The tricorder as a prospecting tool.** Sweep inside the ship first: the
   *Dilithium* line should read 3, from the chamber, which proves it sees
   inside containers. Then sweep in a town -- an electronics store, a pawn
   shop, a garage -- and walk to a ring on the plot.
8. **A crystal is not in the tree.** Search the panel for *dilithium*: nothing
   should come back, in any sandbox mode.
9. **A pattern on a second machine.** One crewman scans; the other's panel
   should stop saying *no pattern* without either of them reopening it.
10. **The sound**, which is played locally and must not draw the dead.
11. **`Unrestricted` and `Off`**, both of which a server owner will use before
    the author does.

---

## What would have bitten you

### The pattern set nearly went into the ship state

`REPLICATOR.md` used to say the pattern set living in `TREK_Ship` was
"probably fine and **not** something to assume", and recommended measuring it
before shipping. Measuring it was not necessary: `Ship.commit()` transmits
the whole table on every change, and `S.serviceVehicle` commits every time the
shuttle is driven one square -- about once a second while anybody is flying
her. Two thousand patterns would have gone down the wire with each of those.

They have their own key and are transmitted only when one is learned. The
reserve is one number, so it stays in the ship state where it belongs.

### The cost model was decided twice

The plan recommended a pattern buffer *instead of* an energy budget, on the
grounds that patterns limit the more interesting thing (what you can make
rather than how fast). The author asked for both, and both is better: the
pattern is a progression and the reserve is a budget, and neither one is a
cooldown wearing a hat. The plan's own alternative -- "worth keeping as a
later layer on top of patterns" -- turned out to be the design.

### Half a machine leaning on a counter

The berth at 0,5 was a steel counter, and the first two versions of this
feature used it: the model hung over it, and what the machine made went into
the counter's own container. That came from the interior refit's note that the
replicator should "arrive as a right-click on an object every save already
has", which was good advice about *migration* and bad advice about what the
thing is.

The author said it twice -- remove the counter, the replicator is the whole
thing -- and was right twice. What it cost to leave it in:

- the model had to float, because a floor-standing unit would be drawn through
  the counter, and a floating model cannot be clicked;
- the output went into a piece of furniture the player could not tell from the
  two identical counters beside it;
- and the deck plan had a container on a square whose fitting was pretending
  to be part of something else.

Taking it out fixed all three and removed code: there is no tray to find, no
tray to count, and no "the tray is full". A fixture that needs another fixture
underneath it to work is not a fixture yet.

### A model drawn above its own square cannot be clicked

The alcove was finished, placed, drawn correctly -- and completely unusable. A
right-click resolves to the floor square under the cursor; the model hangs a
metre and a half above its own square, so aiming at the lit recess named a
square one or two tiles north-west, and the menu -- keyed to the berth -- was
never offered.

Nothing was broken, nothing was logged and every test passed, because the
tests drive a simulated `screenToIso` that cannot model a projection. The
simulation says so about itself, in as many words: *it cannot catch a
projection error; only the game can.* It took one screenshot.

### A refusal that could never happen

The power system shipped with two refusals: *not enough in the reserve* when
spares were still aboard, and *no dilithium* when they were not. The first one
was unreachable from the day it was written -- the swap always covers the cost
-- and nothing said so, because an unreachable branch is not a failing test,
it is a quiet one.

What found it was a mutation: deleting the branch broke nothing. That is the
whole argument for mutation testing in one line. Two things went with it: the
translation string, and the panel's rule for greying its own button, which had
the same mistaken model of the machine and would have refused a press that
would have worked.

### Three renders and a louvred bin

The alcove was authored, rendered, and read as a **wheelie bin**: a louvred
box with a lid. Every fault was invisible in the source and obvious in one
frame (`DEV_GUIDE.md`, *Render it and look*):

- the emitter was 0.24 back, so the recess rendered as a hole straight
  through the unit and the lit panel was a sliver. It sits just inside the
  lip now;
- the lid wore the flanks' louvres, and the game's camera looks down at
  everything. The top has its own panel;
- **the first two renders were of the back of it.** Yaw 0 and 40 show the
  flanks; the opening faces east. Two careful pictures of a box, and the
  fault was in the camera rather than the model.
