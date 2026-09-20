# The replicator

**Built, revision 18. Not yet seen in game.**

A lit alcove over the galley counter that makes any item in Project Zomboid.
Two limits stand between the player and that, and they answer two different
questions:

- a **pattern** decides *what*. The ship can make a thing once it has scanned
  one, which turns looting from "find supplies" into "find the first one".
  Scanning is free and gives the item straight back, and the ship knows its
  own Starfleet gear from the day the world is made;
- **energy** decides *how much*. Every replication spends from a reserve that
  refills itself over about eight game hours, so a night's sleep is a full
  tank and a busy afternoon is not.

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
client   stand at the berth (0,5), right-click it
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
           the reserve covers it
           -> materialise(tray, id, count)   instanceItem, AddItem,
                                             sendAddItemToContainer, and the
                                             tray counted after every one
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
| `shared/TREK/TREK_Replicator.lua` | the catalogue, the blocklist, the patterns, the reserve arithmetic, what a thing costs, where the berth is |
| `server/TREK/TREK_Server.lua` | the three handlers, the tray, `S.replicatorReport()` |
| `server/TREK/TREK_Build.lua` | `furnishReplicator()`, which stands the alcove over the berth once |
| `client/TREK/TREK_ReplicatorUI.lua` | the panel, both menus, the replies |
| `shared/TREK/TREK_Config.lua` | every number, and the sandbox values |
| `TREK_InteriorLayout.lua` | the berth itself: `tag = "replicator"` at 0,5 |
| `tools/gen_replicator.py` | the alcove's mesh and texture, the sound, and the renders |
| `media/scripts/trekshuttle.txt` | `item TrekReplicator`, `model TrekReplicatorModel`, `sound TREK_Replicate` |

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

### The reserve

`C.ReplicatorEnergyMax` (1000) and `C.ReplicatorRegen` (20 per ten game
minutes). Full from empty in 500 game minutes -- eight game hours -- and a
full reserve is two hundred bandages or forty hammers.

**Game minutes, not real ones**, and that is the interesting half. Sleeping
and waiting both work, a server that sat empty overnight does not hand its
crew a free tank the way a wall-clock timer would, and there is no timestamp
arithmetic to get wrong across machines. The cost is one `Ship.commit()` per
ten game minutes while it is charging, which is why the step is ten minutes
rather than one.

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

`C.ReplicatorTag` finds the berth in `TREK_InteriorLayout.lua` -- the steel
counter at 0,5 that the interior refit put there for it. Move the entry in
BuildingEd and the machine follows; rename the tag and it has nowhere to
stand, which `tests/test_layout.py` fails on and `TREK_Replicator()` reports.

The tray is that counter's own container. It is stocked with nothing on
purpose, and the layout test insists on it.

### The alcove

`python tools/gen_replicator.py TrekShuttle/42` writes the mesh, the texture,
the sound and two renders into `design/art/replicator/`. It is **authored
from y = 0.80 upwards** so it hangs above the counter rather than being drawn
through it, and that is the one thing about it to check in game: if the
engine draws world items from the square's floor regardless of where the mesh
sits, the alcove will be sitting on the bench instead of over it. The fix
would be to author from 0 and shorten it.

### The panel

Built from the helm's LCARS parts (`H.pill`, `TREKLcarsButton`, `H.P`), so
the two consoles look like the same ship. `tests/test_helm.py` draws it
against a 122-row catalogue with a name too long for its column.

---

## The rules it obeys

| | |
|---|---|
| The item is created | **Server**, on a validated `replicate` |
| Who may use it | **Server** -- alive, the ship's `canUse`, standing at the machine |
| The pattern set | **Server**, its own mod data key, shared by the crew |
| The reserve | **Server**, ship state, one number |
| The catalogue | **Both**, built per process from the engine's own list |
| The panel, the search, the list | **Client**, presentation only |

- **A client is a request, never a fact.** The id is looked up in the real
  catalogue, the quantity is matched against the list the panel offers, the
  range is measured on the server's own copy of where the player is standing,
  and the inventory a scan reads is the server's copy of it.
- **The tray is counted.** `U.itemCount` before and after every single item,
  because a container at capacity drops what it is handed in silence.
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
python tests/test_multiplayer.py    # replicator() and replicator_multiplayer()
python tests/test_helm.py           # the panel
python tests/test_layout.py         # the berth's tag and its empty tray
python tests/test_assets.py         # the model, the sound, every string
```

`replicator()` plays it the way a player does: it right-clicks the berth,
opens the panel from the menu option, types in the search box and presses the
buttons. Driving the server handlers directly would pass against a build
whose Materialise button was wired to nothing, which is exactly how the
torpedoes once shipped unfireable.

**Nineteen mutations were checked against it and all nineteen caught** -- and
three of those mutations found tests that were passing for the wrong reason:

- the quantity check was "proved" by the reserve, because 999 hammers cost
  more than the ship has. It asserts the *refusal reason* now;
- the sandbox `Off` check ran with a full tray, which refuses by itself;
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
- **A container at capacity is silent.** Count the tray; never trust the
  number you asked for.
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
- **The alcove is a world item**, and world items are saved and deliberately
  preserved by `U.clearSquare`. Anything that places one must look first or it
  stands a second one at every rebuild.

---

## Not built, and still to settle in game

Nothing here has been seen in a game. In the order worth checking:

1. **The way in.** Right-click the counter at 0,5 while standing beside it:
   the option should read *Use the replicator*. It is on
   `OnPreFillWorldObjectContextMenu` because the later event returns early on
   squares the base game finds uninteresting -- but the berth *is* a
   container, so the later event would probably work too. If the option does
   not appear at all, that is the first thing to look at.
2. **The alcove's height.** Authored from 0.80 up so it hangs over the
   counter. If world models ignore that and sit on the floor, it will be
   standing in the counter instead of above it.
3. **The catalogue's real size.** Thirteen items in the simulation and a few
   thousand in the game. `TREK_Replicator()` prints the count; the panel
   should open without a visible pause and the search should stay responsive.
4. **The reserve on the clock.** Sleep a night and watch it come back.
5. **A pattern on a second machine.** One crewman scans; the other's panel
   should stop saying *no pattern* without either of them reopening it.
6. **The sound**, which is played locally and must not draw the dead.
7. **`Unrestricted` and `Off`**, both of which a server owner will use before
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
