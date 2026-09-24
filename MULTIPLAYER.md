# Multiplayer design

How the Shuttlecraft mod works correctly in **single player, hosted co-op and
dedicated servers**, for anyone who subscribes on the Workshop.

Status: **all nine migration steps built (1.3.0)**. Everything through step 8
— the vehicle shuttle and flight — is confirmed in single player and passes the
simulated server with two clients. **Flight was played with two real people for
the first time on 2026-09-23**, which is where the levelling bug in
`PILOTING.md` section 4 came from; nothing else in here has been played with
two real people yet. This document is the plan and the record of why each
decision was made. Every step is covered by `tests/test_multiplayer.py`, which
runs the real Lua as single player and as a server with two clients over a
simulated network, flight included -- but a simulation is not the game.

---

## Hard rules

1. **Works for every Workshop subscriber.** Single player, the in-game Host
   button, and any dedicated server (rented, Linux, anyone's). Nothing may
   depend on a particular PC, launcher, script or server setup. The local
   `PZ-Server.bat` world manager is a *test harness* on the developer's PC and
   nothing more.
2. **Only what the game gives every mod.** The standard `client/`, `server/`
   and `shared/` Lua folders, `sendClientCommand` / `OnClientCommand`,
   `sendServerCommand` / `OnServerCommand`, global and object mod data,
   `media/sandbox-options.txt`. No external tools, no Java patches.
3. **No calls that only work for admins or under `-debug`.** Build 42 gates
   many public methods on role capabilities or `Core.debug` and silently does
   nothing otherwise (`setGodMod`, `setZombiesDontAttack`, `setInvincible`,
   `setNoClip`, `setInvisible`, `setGodModCheat`, the teleport packets,
   `SendCommandToServer("/teleportto")`). A tester with the capability would
   see them work; a Workshop player never does.
4. **One authority per piece of state.** Whatever the server owns, clients
   request and never write. Whatever a client owns (its own character, the
   zombies it simulates), the server does not overwrite.
5. **Every engine call verified** with `tools/pzapi.py` (exists, public),
   `tools/javarefs.py` (what it touches, which gates) and a vanilla call site.

---

## What the engine actually does

Researched from vanilla Lua and the game's bytecode, build 42.20. Confidence
in brackets. These facts drive every decision below.

### Lua loading and roles

- `shared/`, `client/` and `server/` **all load in every process**: single
  player, a co-op host, a co-op guest, and a dedicated server (which runs
  `client/` files too). Vanilla guards with `if isClient() then return end`
  (server files) and `if isServer() then return end` (client files). [HIGH]
- Hosted co-op is **two processes**: the host's game is a client connected to
  a server process it launched. [HIGH]

| Where | `isClient()` | `isServer()` |
|---|---|---|
| Single player | false | false |
| Co-op host's game / co-op guest | true | false |
| Co-op server process / dedicated server | false | true |

So a server-side file guarded by `if isClient() then return end` runs in
**single player and on any server** -- one code path for all three setups.

### Commands

- `sendClientCommand(player, module, command, args)` reaches
  `OnClientCommand(module, command, player, args)` **in single player too**
  (routed through `SinglePlayerServer`). Vanilla relies on it. [HIGH]
- `sendServerCommand(...)` **does nothing in single player** (it only acts
  when `GameServer.server`). The server side must call client logic directly
  when `not isServer()`. [HIGH]

### Global mod data

- Server state lives in `ModData.getOrCreate(key)` and is **saved with the
  world on the server** (`global_mod_data.bin`). [HIGH]
- `ModData.transmit(key)` sends server -> all clients (and is inert in SP).
  **Receiving does not store it**: `OnReceiveGlobalModData(key, data)` fires
  and the handler must `ModData.add(key, data)`. A client can also transmit to
  the server, so the server must never accept state from clients that way.
  [HIGH]

### Building the world from the server

- The server can create squares and objects; `addFloor` and
  `transmitAddObjectToSquare` / `transmitCompleteItemToClients` send them to
  nearby clients, with containers and their items inside the object's save
  data. Vanilla builds furniture exactly this way
  (`server/BuildingObjects/ISSimpleFurniture.lua`). [HIGH]
- Chunks exist on the server **only while a player is near**. Guard every
  square touch with `getCell():getChunkForGridSquare(x, y, z) ~= nil`. [HIGH]
- Containers the mod stocks must be `setExplored(true)` **on the server**, or
  vanilla loot is rolled into them the first time a client opens them. [HIGH]
- Items added later: `container:AddItem(item)` then
  `sendAddItemToContainer(container, item)`. [HIGH]
- `instanceItem(id)` works on the server. [HIGH]
- `isWaterInfinite()` needs the fixture's square to be in a *room* with the
  mains on; the runtime cabin has no rooms, so it never applies. [HIGH]
- **`createFluidContainersFromSpriteProperties` is an empty method.** A
  runtime sink gets water by adding a component, as vanilla's own
  `addWaterContainer` command does:
  `ComponentType.FluidContainer:CreateComponent()`, `setCapacity`,
  `addFluid`, `GameEntityFactory.AddComponent(obj, true, component)`.
  `addFluid` on the object syncs itself. [HIGH]
- The interior's cell (96,40) is inside the server's valid world bounds by
  default (world-gen bounds are -250..+250 cells). [MEDIUM-HIGH -- first thing
  the dedicated-server test checks]

### Moving players

- **There is no legitimate teleport for non-admins.** The only teleport the
  server trusts (`GameServer.sendTeleport`) is unreachable from Lua; every
  route to it is admin-gated. [HIGH]
- A client may move its own character (`teleportTo` / `setX` + `setLastX`).
  On a server with the speed anti-cheat enabled (`AntiCheatSpeed`, default
  **kick**), **each long jump is one strike**; **4 uncleared strikes kick**;
  **one strike clears every 150 s**. [HIGH]
- Anything moving a character faster than **20 tiles/second** on average is a
  strike every second: hands-on flight as built (90 tiles/s at 1x) would be
  kicked in about four seconds. [HIGH]
- Hosted co-op has anti-cheat off unless the host enables it. [MEDIUM]
- Chunk streaming follows the client's reported position automatically. [HIGH]

### Zombies

- **A zombie is simulated by the client that owns it** (the nearest player),
  not by the server. The server copies what the owner reports; if the server
  moves a zombie, the owner's next update overwrites it. [HIGH]
- The synced way to keep zombies back is for **each client to move only the
  zombies it owns** (`not zombie:isRemoteZombie()`). In single player every
  zombie is local. [MEDIUM-HIGH]
- There is no Lua-reachable synced way to delete zombies. [HIGH]

### Vehicles

- A seated character is bitten only when their seat's door is open or
  missing, or its window is broken or missing. **A passenger seat with no
  door part cannot be bitten at all.** [HIGH]
- Vehicles may move up to the server's `SpeedLimit` (default 70 tiles/s)
  without speed strikes. [HIGH]
- **A vehicle's own mod data is never sent to clients.** Build 42 has a
  network field for a *part's* mod data (`VehiclePartModData`) and none for the
  vehicle's, so `vehicle:getModData()` on a client is empty however carefully
  the server filled it in. Anything that identifies a vehicle by a tag the
  server wrote works perfectly in single player and fails on every client of
  every server. `TREK.Vehicle.ship()` therefore falls back to *the shuttle
  standing where the ship is recorded*. [HIGH]
- A vehicle's height is decided by whether a floor exists under its centre
  square, not by its physics body, and the server runs no vehicle physics at
  all. Both facts are set out with the bytecode in `PILOTING.md`. [HIGH]

---

## Architecture

### Who owns what

| State / action | Authority | Why |
|---|---|---|
| The ship (landed?, position, course, bookmarks, shields, owner, crew, build revision, ghost hulls) | **Server**, global mod data `TREK_Ship` | One shared ship per world; must persist and be the same for everyone |
| Cabin geometry, containers, loot, water | **Server** | World objects; clients only see what the server streams |
| Hull world item on the map | **Server** | World object |
| A player's own position (beaming, walking in, arrival hold) | **That player's client** | Only a client may move its own character without admin rights |
| Where a player beamed up from (their return point) | **That player**, player mod data -- and **also the server's copy**, written by the `move` handler before a beam up or a walk in | The client's write never reaches a dedicated server, which then could not say where a player standing in the cabin was: probes aboard were refused for want of a fix. See DEV_GUIDE, *Player mod data a client writes is not the server's* |
| Zombie repulsion (shields) | **Each client**, for zombies it owns | Zombies are client-simulated |
| Phaser charge | **The carrying client** | Items in a player's own inventory |
| Helm, menus, map markers, notes | **Client** | Presentation only |
| Access rules | **Server**, sandbox options | Server owner decides |
| The Doctor standing on the deck | **Server**, `s.emh` in the ship state | A world item, so everyone aboard sees the same one |
| Who may consult him, and who the patient is | **Server**, from its own copy of where people are standing | A client is a request, never a fact -- including about whose body it is |
| **Any body the EMH treats or cures** | **Server**, written directly and pushed with `syncBodyPart` | Forced by the engine: `BodyDamage.Update()` restores a *remote* player's body to full on a client every tick, so the server is the only machine that knows they are hurt |
| The body-level infection flags and the infection moodle | **The patient's own client**, on `emhCured` | `syncBodyPart` carries `BodyPart` fields only; the `BodyDamage` flags and the moodle do not ride it |
| Consent to be treated | **The patient's client** raises it; the server mints, expires and re-validates the token | Nobody can force-heal, or force-anything, another player |
| The crystal and the cure register | **Server**, ship state, one writer | Paid for, and it has to survive a relog |
| The light at the EMH's square, his panel and his portrait | **Each client, for itself** | Scenery and presentation, like the cabin's lamps |
| Distress calls, rescues, the downed ensign's figure and the clock | **Server**, in the contact store (`TREK_Contacts_v1`) beside the contacts | A mission is shared ship knowledge; the figure is a world item; the clock has to run with nobody near (ENSIGN.md) |
| The ensign's beacon (`addSound`) | **Server** | It moves zombies, which is world state |
| The ensign's combadge chirp | **Each client, for itself** | Presentation: what this machine hears |
| A PADD's library | **Server**, in a timed action's `complete()`, pushed to the carrier with `syncItemModData` | Item state; every Lua timed action on a client is rebuilt and completed on the server (PADD.md section 7) |
| What reading off a PADD gives | **Server**, in `TREKReadPadd:complete()`; a novel's comfort also on the reader's client via `paddRead` | Exactly where vanilla applies a book |

### Files

```
media/lua/shared/TREK/    config, util, state schema, protocol names -- no side effects
media/lua/server/TREK/    authoritative logic: ship state, build, stock, water, hull, commands
                          every file starts: if isClient() then return end
media/lua/client/TREK/    UI, menus, own-character movement, shields, phaser
                          every file starts: if isServer() then return end
media/sandbox-options.txt server-owner settings
```

### State

`TREK_Ship` (global mod data, server-authoritative):

```lua
{
  schema = 2,
  landed = bool, x, y, z,          -- where the hull stands when landed
  destination = { x, y, z } | nil,
  bookmarks = { {name, x, y, z}, ... },
  shields = bool,
  owner = username | nil,          -- first to claim; admins may reassign
  crew = { username = true, ... },
  built = bool, rev = n,
  ghosts = { {x, y, z}, ... },
}
```

The server calls `ModData.transmit("TREK_Ship")` after every change. Clients
`ModData.request` on world load and `ModData.add` on receive. **Clients never
edit it**: every change is a command.

Per player (`player:getModData().TREK`): `returnX/Y/Z`, `aboard`.

### Protocol

Module name `TREK`. A shared helper `TREK.Net.toClient(player, cmd, args)`
calls `sendServerCommand` on a server and the client handler directly in
single player -- the one place that difference lives.

Client -> server (`OnClientCommand`), each validated server-side (access rule,
sane numbers, player alive):

| Command | Server does |
|---|---|
| `boarded` | Marks the player aboard; builds or repairs the cabin once its chunks are loaded around them |
| `setCourse {x,y}` / `clearCourse` | Updates the course |
| `addBookmark {name,x,y,z}` / `removeBookmark {index}` | Updates bookmarks (name length-limited) |
| `setShields {up}` | Updates shields |
| `landAt {x,y,z}` | Runs the landing search around a player standing there; places the hull or refuses with a reason |
| `callDown {x,y,z}` / `recall` | Same, from the ground |
| `refillWater` | Tops up the cabin's plumbed fixtures |
| `claim` / `setCrew {name, on}` | Ownership and crew, if access rules allow |
| `emhSummon` / `emhDismiss` | Projects the Doctor onto 2,4, or takes him down; `s.emh` is the truth and `B.serviceEMH` makes the deck match it |
| `emhLook {who}` | Reads that patient's body and answers `emhFindings` -- the panel cannot read a remote body itself |
| `emhTreat {who}` / `emhCure {who}` | Treats or cures; naming somebody else mints a consent token and asks **them** |
| `emhAccept {token}` / `emhDecline {token}` | The patient's answer, re-validated from scratch |
| `distressAnswer {id, accept}` | Accepts or declines the pending distress call; the id must be the call that is pending, and the player aboard by the server's copy |
| `rescueEnsign {id}` | Beams the downed ensign to safety: live, placed, within reach by the server's copy, figure present -- then one removal, one status change, one reward |

Server -> client (`OnServerCommand` / direct in SP):

| Command | Client does |
|---|---|
| `landed {x,y,z}` / `landingRefused {why, blocked}` | Notes, and the beam-back if refused |
| `cabinReady` | Ends the arrival hold |
| `denied {why}` | Explains a refused request (access, transporter charge) |
| `emhFindings {who, total, infected, bitten, items}` | What the Doctor can see about a patient this client cannot read |
| `emhOffered {token, from, what, cost}` | To the **patient**: a yes/no |
| `emhTreated {who, counts, total}` | What he put right |
| `emhCureStarted {hours}` / `emhCured` / `emhCureLost` | The cure beginning, landing (clear your own flags and moodle) or being abandoned |
| `distressCall` / `distressAccepted` / `distressDeclined` / `distressLapsed` | A call arriving (note and chime), and what became of it |
| `ensignRescued {name, by, learned}` / `ensignLost {name, why}` | How a rescue ended |
| `paddRead {entry}` | The reader's client applies a novel's comfort to itself, as vanilla's `literature.readLiterature` does for a paper book |

---

## Systems

### Cabin build, loot and water (server)

- Built by the server when a player reports `boarded` and the cabin's chunks
  are loaded around them; repaired on the same trigger when `rev` is stale.
- Objects created with the server pattern: `IsoObject.new` -> tag in object
  mod data -> containers created and `setExplored(true)` and stocked ->
  added with `transmitAddObjectToSquare` (or `addFloor`). One send per object.
- Stock-once rule unchanged (object mod data `TREKStockRev`).
- The void margin is cleared server-side as chunks load.
- Water: the sink gets a `FluidContainer` component (vanilla's
  `addWaterContainer` pattern) and is topped up with `addFluid`, which syncs.
  Refilled on a server timer while anyone is aboard.

### Transporter and boarding (client moves, server charges)

- The beaming client moves its own character (`teleportTo`, then exact
  position), exactly as today, and tells the server `boarded` / left.
- **Transporter charge.** On a server whose `AntiCheatSpeed` would kick or ban
  (read with `getServerOptions():getOption("AntiCheatSpeed")`: 1 ban, 2 kick,
  3 log, 4 disabled), each player has **3 charges, one restored every 150 s** -- the anti-cheat's own budget,
  so the mod refuses the 4th beam in-lore ("the transporter is recharging")
  instead of the server kicking the player. In single player, co-op without
  anti-cheat, or with the check set to log/off, charges are unlimited.
- Walking out of the hatch is also a long move, so it spends a charge too.
- Taking her down needs 2 charges and spends 1: the other is held for the
  beam home if there is no room to land (`recover` is free).
- **Beaming down arrives first, then settles** on the nearest clear square:
  the ground at the destination is not loaded -- on the client or the server
  -- until someone stands there.
- A server owner can remove the limit entirely with `AntiCheatSpeed=3` (log)
  or `4` (off); the Workshop description says so.

### Hull, landing, recall, ghosts (server)

- The landing search needs the site's chunks, which the server has only near
  a player -- so, as today, **the player beams to the site first**, then asks
  the server to land. Refusal beams them back.
- Hull world item placed and removed on the server; ghost-hull sweep runs on
  the server as players load chunks.

### Helm (client UI, server state)

- Unchanged UI; every button sends a command instead of writing state, and
  redraws from `TREK_Ship` as it arrives.

### Shields (each client, own zombies)

- Every client near the landed hull runs the push, skipping
  `isRemoteZombie()` zombies; single player pushes all. Reads `shields` and
  the hull position from `TREK_Ship`.

### The sky plane (each client, its own copy)

Flight is driving on an invisible floor laid at altitude, and **each client
lays its own**. That is a deliberate exception to "a client never edits the
world", and it is narrower than it sounds:

- build 42's server runs **no vehicle physics at all** — `setPhysicsActive` and
  `setWorldTransform` both skip their `Bullet` calls when `GameServer.server` —
  so the server has no use for a floor;
- the driver's client needs one to drive on, and every client needs one to draw
  the ship in the air; all of them derive it from the same synced vehicle
  position, so they agree without a packet;
- it is only ever `invisible_01_0`, only ever above ground level, and it is
  always taken up again — the same class as the cabin's lights and powered
  squares, which every client also makes for itself.

The ship's *state* is untouched by this: `flying`, `level` and `pilot` are the
server's, set by validated commands, exactly like everything else.

### Phaser (carrying client)

- Unchanged in principle: top up the charge of phasers in the local player's
  own inventory, only for local players (`isLocalPlayer`). *Verify on a
  dedicated server* that the charge sticks.

### Access and ownership (server, sandbox options)

`media/sandbox-options.txt`, page **Shuttlecraft**:

| Option | Values | Default |
|---|---|---|
| `TrekShuttle.Access` | Everyone / Owner and crew | Everyone |
| `TrekShuttle.TransporterLimit` | Match anti-cheat / Always unlimited | Match anti-cheat |
| `TrekShuttle.TorpedoFire` | Full / Blast only | Full |
| `TrekShuttle.Replicator` | Patterns and energy / Unrestricted / Off | Patterns and energy |
| `TrekShuttle.EMH` | Full / Off | Full |

- **Owner**: the first player to use the ship claims it -- on a hosted game
  that is naturally the host. Admins can reassign; the owner manages the crew
  list from the helm.
- With **Everyone**, ownership only decides who manages the crew list.

---

## Flight -- what was built

**Decision (2026-09-17): C, the shuttle is a vehicle the crew enters like a
car** -- and it flies. Entering a vehicle is not a teleport and takes no
anti-cheat strike, an occupant may travel at the server's vehicle speed limit,
a seat with no door cannot be bitten, and vehicle position is synced by the
game itself. Everything hands-on flight had to fake, the engine already does.

She flies by **driving, on an invisible floor the mod lays at altitude**, for
reasons that are entirely forced: see `PILOTING.md`, which has the bytecode.
What matters here is the authority split.

| | |
|---|---|
| `flying`, `level`, `pilot`, `speed` | **Server**, ship state, set only by validated commands |
| Who may take off and land | **Server** -- alive, `mayUse`, and in the driver's seat |
| The lift, and keeping her level | **The client that owns the physics** (`isLocalPhysicSim`) |
| The invisible floor | **Each client, for itself.** Never synced. |
| Sending her back up when nobody is aboard | **Server**, on its own copy of where everyone is standing |
| Driving, steering, seats, camera, position sync | **Vanilla.** The mod touches none of it. |

`takeoff` -> `takeoffGranted` -> *(the client paves, lifts, and reads the
height back off the engine)* -> `airborne` -> `setSpeed` -> `touchdown` ->
`touchdownGranted`, with `flightEnded` to everybody. **The server never records
her as flying until a client reports that the engine actually held the
height**: a lift that failed must not leave the state saying she is up when she
is sitting on the grass.

**Flight is a binary**: she is on the ground or she is hovering at
`C.FlightLevel`, and there is no `setAltitude` on either side. It was four
levels with *Climb* and *Dive* on the radial; only two of the four ever behaved
in play, and the command was removed rather than left as a handler that accepts
a request and quietly does nothing. `PILOTING.md` section 1 has why level 1 in
particular is the one the engine will hold.

**And nobody aboard means she goes back up, not down.** The hatch is shut while
she hovers, so the only way out of her is the transporter; when the last of the
crew beams down, `S.endFlight(why, toOrbit)` clears the flight and `S.toOrbit`
removes the vehicle and sets `landed = false` -- the same state a recall leaves
her in. Dropping her onto whatever happens to be underneath was the
alternative. The crew are told, because a ship that disappears without a word
is indistinguishable from one that has been lost.

The test for who counts as aboard asks about **everybody**, not the recorded
pilot: on a server the pilot may beam down while a crewman is still aft, and
pulling the ship out from under them would leave them in a cabin belonging to
nothing.

**And it runs whether or not her chunk is loaded**, which is the multiplayer
half of it and the thing that broke in play. Chunks stream only around players,
so the server's copy of the vehicle is missing exactly when nobody is near her
-- exactly the case the watchdog exists for. Gated on the vehicle being there,
it never fired, and a crew who beamed down and walked away left her flying for
ever, with the hatch and the recall both refusing them. `crewAboard(nil)` is
correct: a player in a seat keeps her chunk loaded by being in it, so an
unloaded ship has nobody in a seat by definition, and the cabin test needs no
vehicle at all.

Two graces, for the two gaps a beam leaves. `FlightPilotGrace` covers a player
who is briefly in neither the seat nor the cabin. `FlightBoardingChecks` is set
by the server the moment somebody is *granted* a beam towards a hovering ship,
because on a real connection the ground at the far end can take far longer to
stream in than the beam itself.

### Why a client may lay world floor

This is a documented exception to hard rule 4, and a narrow one.

- The **server runs no vehicle physics** in build 42 -- `setPhysicsActive` and
  `setWorldTransform` both skip their `Bullet` calls when `GameServer.server`
  -- so it has no use for a floor and never lays one.
- The **driver's client** needs one to drive on; **every** client needs one to
  draw her in the air. All of them derive it from the same synced vehicle
  position, so they agree without a packet crossing the network.
- It is only ever `invisible_01_0`, only ever above ground level, and always
  taken up again. It is scenery and local physics -- the same class as the
  cabin's lights and powered squares, which each client also makes for itself.
- The ship's *state* is untouched by any of it.

`tests/pz_sim.lua` counts sky floors separately from every other client world
edit, so "no client ever edits the world" keeps its teeth for everything else,
and the two-player scenario asserts both machines see her at altitude and that
neither made any other edit.

### Photon torpedoes

Built and confirmed in game (2026-09-20). `PHOTON_TORPEDOS.md` is the working
guide; this section is only the client/server half.

The two verify-first questions were "killing a zombie has to be done by the
server" and "the explosion must not set the street on fire". The first stands.
**The second was a misreading** -- it meant fire as an intended weapon effect,
and was taken to mean no fire at all, which cost the feature its entire visible
half for three commits. A torpedo burns, deliberately. See
`PHOTON_TORPEDOS.md`, "How it came to be invisible".

**The route is `IsoTrap`**, which clears all three bars this project sets --
public (`pzapi.py`), understood under-what-condition (`javadis.py`), and with a
real vanilla Lua call site (`shared/TimedActions/ISPlaceTrap.lua:47`,
`IsoTrap.new(character, weapon, cell, square)` then `trap:place()`).
`IsoTrap` is on `LuaManager$Exposer`'s allow-list.

**Fire is where the whole picture lives**, and this paragraph used to say the
opposite. `drawCircleExplosion` in `Explosion` mode does exactly this:

```java
boolean startFire = Rand.Next(100) < getFireStartingChance();   // bci 197-214
boolean burn      = Rand.Next(100) < getFireStartingChance();   // bci 254-271, a SECOND roll
if (!GameClient.client && getExplosionPower() > 0 && burn)
    square.Burn();                                              // bci 293
explosion(square);                                              // bci 299 -- always
if (startFire) IsoFireManager.StartFire(...);                   // bci 316
```

**There is no separate explosion effect in build 42**: `explosion(square)` is
the damage and it is unconditional, and everything a player *sees* is the fire
and the smoke. So `FireStartingChance = 0` does not make a tidy explosion, it
makes an invisible one. Vanilla's `PipeBomb` does ship 0 -- because a pipe bomb
is not meant to be arson, and a photon torpedo is.

Two corrections to what this section said before: the two fire paths take
**independent** rolls, not one shared one (bci 197 and bci 254); and
`triggerExplosion()` calls `drawCircleExplosion` three separate times, skipping
any mode whose range is `<= 0`, so a zeroed `FireRange` or `SmokeRange` never
runs at all rather than running quietly.

`Burn()` -> `BurnWalls(true, true)` is what destroys structures. It returns
immediately on a client, so it is server-authoritative for free, and it checks
`ServerOptions.noFire` and `SafeHouse.isSafeHouse` itself. The obvious call,
`IsoFireManager.explode`, is still the *wrong* one: unconditional `StartFire`
plus `BurnWalls`, and it touches no character at all. [HIGH]

**The engine already enforces this document's zombie rule.**
`IsoTrap.shouldProcess(character)` decides who a blast may damage:

| Running as | Zombies | Players |
|---|---|---|
| Single player | all | yes |
| **A client** | only `isLocal()` ones | never |
| **The server** | **all** | per `ServerOptions` (PvP) |

That is the same ownership rule the shields follow, written into the engine.
Damage goes through `IsoMovingObject.Hit(HandWeapon, attacker, damage, false,
1.0)` -- the ordinary synced hit path -- and `drawCircleExplosion` already
respects `LosUtil.lineClear` (walls block it) and `NonPvpZone`. [HIGH]

So the authority split needs no exception:

| | |
|---|---|
| Firing, cooldown, and the blast | **Server**, on a validated command |
| Who may fire | **Server** -- alive, `mayUse`, in the driver's seat, flying |
| Aiming, the reticle, the UI | **Client**, presentation only |

`fireTorpedo {x, y, z}` -> the server checks the pilot, the cooldown and both
range bounds, then **queues** the shot and broadcasts `torpedoLaunched` so every
client can draw the flight. On arrival it builds an `IsoTrap` at the target
square with the explosion and the four fire settings, triggers it, and
broadcasts `torpedoDetonated`. Because the server processes every zombie and
each client processes only its own, the trigger must be **server-only** or a
zombie owned by a client would be hit twice.

The projectile is **scenery**, the same documented exception as the sky plane:
each client draws its own from that one packet, in screen space, touching no
world object at all. The fire needs no packet of ours -- `IsoFireManager
.StartFire` sends its own to nearby clients.

Still unproven, and only the game can say: whether the blast is visible to a
client that did not fire it, and what it does to the shuttle if fired too
close.

### The medical set

Built 2026-09-20, not yet played. `MEDICAL_SET.md` is the dev guide; this
section is only the authority split.

| | |
|---|---|
| Treating your **own** body (the hypospray, the dermal regenerator) | **That player's client.** Body damage belongs to the owning client and syncs from there -- the same rule and the same reason as "a client moves only its own character" |
| Hypospray doses | **The item**, in its own mod data, which travels with it |
| Reading your own vitals (medical tricorder) | **Client.** Pure UI |
| Reading **somebody else's** vitals | **The engine's own consent flow.** `requestMedicalCheck` raises a yes/no on the other player's screen; only a yes reaches `ISMedicalCheckAction`, which the mod wraps to raise `doctorLevel` |
| The sensor sweep | **Each client, for the zombies it can see.** Reads `cell:getZombieList()`, the same list the shields walk. On a server that is not quite every zombie there is, which is honest -- a sensor reading rather than omniscience |
| The contact plot | **Client**, drawn in the panel; it touches no world object, the same documented exception as the torpedo's flight |
| **A lock** | **Server**, on a validated `unlock` command |

Three things about the lock are worth keeping here rather than only in
`MEDICAL_SET.md`:

- **The engine's own sync runs on the wrong side.** `setLockedByKey(b)` fires
  `IsoDoor.sync()` itself, behind `if (!GameServer.server)`. A lock is world
  state, so by hard rule 4 the server is what changes it -- and that is
  exactly the process where the branch is skipped. `obj:sync()` is the
  explicit call that works from both, and the server makes it. [HIGH]
- **The tool is checked in the player's inventory on the server's own copy**,
  not taken from the command, along with the range, the cooldown and whether
  the chunk is even loaded. A client is a request and never a fact.
- **It will not open a padlock, and it will not open anything inside a
  safehouse the asking player is not a member of.** Both are another player's
  property. A mod that picks them is a griefing tool on every server that
  installs it, with no setting to turn it off, because a server owner would
  first have to know it was there. `SafeHouse.isSafeHouse(square, username,
  true)` answers exactly that question: it returns the safehouse only when the
  named player is not on its list. [HIGH]

`tests/test_multiplayer.py` plays all of it, single player and with two
clients, including the refusals and the one check that asserts a non-effect: a
dose must leave a bite and the zombie infection alone.

### The replicator, and the power behind it

Built 2026-09-20 and played the same day; the dilithium that powers it is
built and not yet played. `REPLICATOR.md` is the dev guide; this section is
the authority split and the one piece of engineering that is not obvious from
it.

| | |
|---|---|
| The item is created | **Server**, on a validated `replicate` command. This is the one feature in the mod that can hand a player anything in the game |
| Who may use it | **Server** -- alive, the ship's own `canUse`, and standing at the berth, measured on the server's copy of where they are |
| The pattern set | **Server**, its own global mod data key, shared by the crew |
| The reserve | **Server**, ship state: one number. A client with no copy yet reads it as full rather than empty, so a panel opened before the first sync does not grey its own button |
| The crystals | **Server**, ship state: one number beside the reserve. They were items in a container for one revision; the core is the mod's own model and a model cannot have a container, and the number turns out to be the better half of the trade -- every client knows the spare count without standing in front of anything |
| Loading one in | **Server**, on `loadCrystal`. It looks in its own copy of the player's inventory, filtered on the **full** id, removes the crystal, counts the inventory before and after, and follows it with `sendRemoveItemFromContainer` so the asking client's own copy agrees |
| Taking one out | **Server**, on `takeCrystal`. The crystal is made into the player's hands and **counted first**; the ship's number only goes down once one really landed |
| Loading a spare | **Server**, inside `P.afford`, which is guarded by `isClient()` -- a client asked to pay for something it cannot afford simply answers no |
| The catalogue | **Both**, built per process out of `getAllItems()`. It is derived from the game's own scripts, so every process computes the same thing and none of it crosses the wire |
| The panel, the search, the list | **Client**, presentation only |

**The pattern set is deliberately not in `TREK_Ship`.** `Ship.commit()`
transmits the whole ship table on every change, and `S.serviceVehicle` commits
each time the shuttle is driven a square -- roughly once a second while
anybody is flying her. A crew who have scanned two thousand items would push
two thousand strings through every one of those. It has its own key
(`TREK_Patterns_v1`) and the same request-and-receive handshake as the ship,
and it is transmitted only when a pattern is actually learned. `DEV_GUIDE.md`
has it under *State that is transmitted whole cannot hold a list that grows*.

Three things the server does not take a client's word for: the **id** (looked
up in the real catalogue, never handed to `instanceItem` blind), the
**quantity** (matched against the list the panel offers, or the command is an
item printer), and the **inventory** a scan reads (its own copy, via
`getAllEvalRecurse`).

**What it makes goes into the asking player's own inventory**, which is the
engine's own idiom rather than an invention: `server/ClientCommands.lua` does
`player:getInventory():AddItem(item)` followed by
`sendAddItemToContainer(player:getInventory(), item)` in a dozen places, on a
validated client command -- exactly this shape. The inventory is counted
before and after every single item, because `instanceItem` answers nil for an
obsolete item that slipped the filter and a container at capacity drops what
it is handed, and from the server's side both look like success.

---

## Risks that only the game can settle

1. The interior cell loads on a **dedicated server** (bounds) -- test first.
2. The server-built cabin streams to clients with containers and loot intact.
3. The sink's added `FluidContainer` works with the mains off.
4. Beam counts versus kicks on a server with `AntiCheatSpeed=2`.
5. Two players aboard at once: both see the same cabin, loot taken by one
   disappears for the other.
6. Phaser charge persists on a dedicated server.
7. Shields push zombies for every client near the hull.
8. **A shuttle in the air, seen from the other machine.** Each client lays its
   own floor under her and derives the level from it, and the simulated
   two-client scenario says both see her at altitude -- but the engine's own
   half of that (`clientUpdateVehiclePos` writes `setZ(0)` and
   `BaseVehicle.update()` then recomputes it) has only been reasoned about.
9. **Flight speed at one helm reaching the pilot at another.** Proven in
   simulation; unproven across a real connection.
10. **The heading she is flown on, seen from the other machine.** The levelling
   pass runs on every client that can see her and only the physics owner moves
   her, and the first two-player flight found that pass wrenching her rotation
   to the identity whenever the pilot turned more than a quarter turn --
   `getAngleX` reads 180 there for a ship that is dead level (`PILOTING.md`
   section 4). Fixed and covered in simulation on both machines; the real
   connection has not seen it since.
11. **A lock opened by one player, seen by another.** The server clears the
    flags and calls `obj:sync()`; the packet itself has only been reasoned
    about from the bytecode.
12. **A medical scan on another player**: the consent prompt appearing on
    their screen, and the panel that follows reporting at doctor level
    rather than at the scanner's own Doctor skill.
13. **A pattern scanned by one player appearing for another**, which is the
    only thing the replicator's separate mod data key has to get right: the
    server transmits `TREK_Patterns_v1` when a pattern is learned and each
    client stores what arrives. The simulated two-client scenario agrees.
14. **An item the server makes arriving in the asking player's hands**, and
    in nobody else's. It rides `sendAddItemToContainer` on their own
    inventory, which is what vanilla's ClientCommands.lua does -- but on a
    real connection rather than a simulated one.

---

## Test plan

| Setup | How | Covers |
|---|---|---|
| Single player | Fresh world, *Water Shutoff: Instant* | Everything, one player |
| Dedicated server | Local test world with only the dev build enabled; host joins at 127.0.0.1 | Bounds, server build, streaming, charges, phaser |
| Two players | Second client (Steam Deck on LAN) on the dedicated server | Shared cabin, loot, shields, access, **and flight seen from both** |
| Hosted co-op | In-game Host (not reliable on the developer's PC; test when possible) | Same code as dedicated |

Static: `tests/test_multiplayer.py` loads `server/` and `client/` under lupa
with the network stubbed and plays the mod as single player and as a server
with two clients. It checks that every command a client sends has a server
handler that validates it, that no client file writes `TREK_Ship`, and that no
client edits the world except the sky plane. Its two-client scenario flies her:
take-off, both machines seeing her at altitude, the speed set at one helm
reaching the pilot at another, a passenger refused the controls, and a dead
pilot bringing her down.

**Mutation-check anything added there.** Several of these guards passed their
first run for the wrong reason, because the simulation was being kinder than
the engine -- it had no vehicle gravity, no floor-gated height, and no
one-frame delay on the radial menu until each of those let a real bug through.

---

## Migration order

Each step left single player working, was tested, and was committed. **All nine
are done**; what remains is playing it with two people.

1. **Foundations**: `shared/TREK/TREK_Net.lua` (protocol names, toClient
   helper), state schema 2 with migration from single-player saves, file
   guards, sandbox options.
2. **Server build**: cabin, loot, water moved to `server/`; client arrival
   hold waits for the server.
3. **Ship state and helm**: course, bookmarks, shields, access through
   commands.
4. **Transporter**: charges; own-character movement unchanged.
5. **Shields**: owner-only zombie push.
6. **Remove hands-on flight** (unsafe, and kicked in multiplayer); travel by
   the helm in the meantime.
7. **Shuttle vehicle, stage 1**: vehicle script and model, doorless seats,
   server spawns and removes it for landing, call down and recall; replaces
   the world-item hull.
8. **Shuttle vehicle, stage 2**: lift-off and flight.
9. **Tests and docs**: the two-client scenario, DEV_GUIDE, README
   (server-owner notes), and `PILOTING.md` for how flight works and why.
