# Installations: Starfleet machines in your own house

The working guide to installing a replicator, a Doctor's station and the warp
core that powers them anywhere in the world (a farmhouse, a gun shop, a
police station) so a base of the player's own can run like the ship. Asked
for by the author on 2026-09-27: "players should be able to make their
regular house Starfleet powered".

**Not seen in game yet.** Section 8 is what to check.

---

## 1. What a player gets

- **Three kits**, each an item you carry: a **warp core** (heavy), a
  **replicator** and an **EMH station**. The ship's replicator knows all
  three patterns from the start, so a commissioned shuttle can make them;
  the field station's stores hold a set in every crate.
- **Right-click a kit in your inventory: *Install here*.** The machine goes on
  the square in front of you (the warp core on the two by two in front of
  you), backed onto a wall if there is one. The kit is used up.
- **The warp core is the power.** It starts empty: right-click it and *Load a
  dilithium crystal*, as the shuttle's is loaded. Everything installed within
  25 squares of it, and up to three storeys above or below, runs on it.
- **The replicator** works exactly as the shuttle's does, the same patterns,
  the same panel, billed to the nearest core.
- **The EMH station** projects the Doctor in front of it, always up while the
  core has power: treatment, the cure (you stay within the core's reach for
  the twelve hours) and the detox, as in the shuttle's sick bay.
- **Right-click an installed machine: *Dismantle*.** It comes off and you have
  the kit back; a core gives back every crystal still in it.
- **The map, the lights and everything else about the house are the house's.**
  Installations are machines, not a ship: there is no transporter, no shields,
  no hull.

## 2. The rules

| | |
|---|---|
| Where you may install | Anywhere with a floor, loaded, not on a runtime deck (the cabin, the Adirondack, the field station; they have their own) and not in somebody else's safehouse |
| What the square must be | Free: no wall, furniture or anything solid standing on it (every square, for the core) |
| Which core a machine runs on | The **nearest** installed core within 25 squares across and 3 storeys up or down, decided when it is used, so moving a core moves what it powers |
| A machine with no core in reach | Installed and dark: its menu says *No warp core within reach* |
| Who may use them | Anybody standing at them. The shuttle's *Owner and crew* setting is about the shuttle, not your house |
| Power | Each core is its own store (pool `i<id>`): its reserve, its spare crystals, dark when both are gone. Nothing in a house ever bills the shuttle, the Adirondack or the station, or the other way round |

## 3. How it works

**One registry, on the server.** `TREK_Installations` global mod data:

```lua
{ next = 4,
  cores    = { [1] = { x, y, z, power, crystals, dark } },
  machines = { [2] = { kind = "replicator", x, y, z, facing },
               [3] = { kind = "emh_station", x, y, z, facing } } }
```

Published to every client (the replicator's patterns' handshake: requested on
load, stored on receipt), whenever something is installed or dismantled, and
whenever a core's numbers change, checked once a second on the server
against what was last sent, because the charges that move them are the ship's
own code and commit the ship state, not this.

**The machines are the Adirondack's tiles** (`trek_adirondack_02`: the
replicator, the EMH station, the 2x2 warp core), placed as world objects
tagged `inst`, which is what a dismantle looks for and what no builder of ours
ever strips. They cannot be picked up (`BUILDING.md`, `FIXED`): a machine is
found by where it stands. The Doctor is the ship's world model, stood in front
of his station at install and taken away at dismantle.

**The existing machines just gained a third place to be.** Every question
that used to be "the cabin, or the Adirondack?" now also asks the registry:

| Question | Where it is asked |
|---|---|
| Standing at a replicator | `R.inReach` |
| Clicked a replicator | `TREK_ReplicatorUI`, `isBerth` |
| Standing at / clicked the Doctor's station, is he up | `E.inReach`, `E.isStation`, `E.isUp` |
| Standing at / clicked a core | `P.inReachOf`, `TREK_WarpCore.isCore` |
| Whose power | `P.poolOf`: a runtime site, else the nearest core's pool, else the shuttle |
| Who is "here" for the Doctor | `E.patients`, `E.aboardForCure`: the same core's reach |

`TREK_Net` already serves every command under `P.poolOf(player)`'s store, so
the replicate, load, take and every EMH command bill the right core with no
change of their own.

**Kits** are three items (`TrekReplicatorKit`, `TrekEMHKit`,
`TrekWarpCoreKit`), icons rendered from the machines' own tiles
(`tools/gen_kit_icons.py`).

## 4. Who owns what

| | |
|---|---|
| The registry, every core's numbers | **Server**, `TREK_Installations`, transmitted to clients |
| Installing | **Server**, on `installMachine {kind, x, y, z}`: the kit taken from its own copy of the inventory (counted), the squares checked, the object placed and sent |
| Dismantling | **Server**, on `dismantleMachine {id}`: in reach on its own copy of the player, objects removed, kit (and crystals) made into their inventory and counted |
| Using a machine | Exactly as aboard: the ship's handlers, under the core's pool |

## 5. Files

| File | What |
|---|---|
| `shared/TREK/TREK_Installations.lua` | the registry, reach, which core, the pool's box |
| `server/TREK/TREK_InstallationsServer.lua` | installing, dismantling, publishing |
| `client/TREK/TREK_InstallationsUI.lua` | the kit's *Install here*, the machines' *Dismantle* |
| `TREK_Replicator.lua`, `TREK_EMH.lua`, `TREK_Power.lua`, `TREK_WarpCore.lua`, `TREK_ReplicatorUI.lua`, `TREK_EMHUI.lua` | the third place |
| `media/scripts/trekshuttle.txt` | the three kits |
| `tools/gen_kit_icons.py` | their icons |

## 6. Testing

```sh
TREK_ONLY=installations,installations_multiplayer python tests/test_multiplayer.py
python tests/test_assets.py      # the kits, their icons, IN.Sprites against the sheet
```

**`installations()`**: the ship knows the three kits; a core refused on a
square with a locker on it (the kit kept); installed, dark, loaded by hand to
lit; a replicator beside it making a ration on the core's power and not the
shuttle's; an EMH station with exactly one Doctor in front of it, up and
willing; a replicator with no core in reach refused (with the shuttle
powered, so the guard and not an empty reserve refuses) and its menu
saying why; a core refused dismantling from across the map, and beside it
giving back its kit and its spare crystal.

**`installations_multiplayer()`**: alice installs a core and a replicator;
bob's client is told of the core and sees it lit once loaded; bob replicates
on it.

**Eleven mutations, one at a time, all caught**, one only after its test
was tightened twice: the lonely replicator's refusal was hidden first by an
unpowered shuttle and then by the replicator's own cooldown.

`tests/pz_sim.lua` learned for it: a square is not free with something
solid on it (`SIM.tileProps`), a wall on an edge, and which way a player
faces. Before, every square was free: a stub that would have let a warp
core stand on a wardrobe.

**Caught in writing the test, not in the game:** the kit's *Install here*
option passed its arguments one place along (vanilla calls `onSelect(target,
param...)`), so it would have done nothing at all.

## 7. Open

- Kits cost what their weight costs at the replicator. A warp core kit is the
  heaviest thing the mod makes; whether that is expensive enough is for play.
- No limit on how many cores a world holds. The registry is transmitted whole,
  so a thousand would be a thousand rows on every change.

## 8. Not yet seen in game

1. Replicate the three kits on the shuttle (or take a set from the field
   station's stores).
2. Install a core in a house, load a crystal: the core lit.
3. Install a replicator beside it and make something. The shuttle's reserve
   does not move.
4. Install the EMH station: the Doctor stands in front of it; treat.
5. Dismantle each: the kit back, the core's crystals back.
6. Two players: one installs, the other uses.
