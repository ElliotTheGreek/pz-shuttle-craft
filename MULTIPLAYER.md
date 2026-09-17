# Multiplayer design

How the Shuttlecraft mod works correctly in **single player, hosted co-op and
dedicated servers**, for anyone who subscribes on the Workshop.

Status: **migration steps 1-6 built (1.3.0), awaiting in-game test**; the
vehicle shuttle (steps 7-8) is next. This document is the plan and the record
of why each decision was made. Steps 1-6 are verified against
`tests/test_multiplayer.py`, which runs the real Lua as single player and as a
server with two clients over a simulated network -- not yet in the game.

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

### Vehicles (for a future flight)

- A seated character is bitten only when their seat's door is open or
  missing, or its window is broken or missing. **A passenger seat with no
  door part cannot be bitten at all.** [HIGH]
- Vehicles may move up to the server's `SpeedLimit` (default 70 tiles/s)
  without speed strikes. [HIGH]
- Moving a vehicle freely is physics-driven on the driver's client, the
  engine re-enables physics and snaps height to the floor, and nothing in
  vanilla does it. [LOW-MEDIUM: feasible, unproven]

---

## Architecture

### Who owns what

| State / action | Authority | Why |
|---|---|---|
| The ship (landed?, position, course, bookmarks, shields, owner, crew, build revision, ghost hulls) | **Server**, global mod data `TREK_Ship` | One shared ship per world; must persist and be the same for everyone |
| Cabin geometry, containers, loot, water | **Server** | World objects; clients only see what the server streams |
| Hull world item on the map | **Server** | World object |
| A player's own position (beaming, walking in, arrival hold) | **That player's client** | Only a client may move its own character without admin rights |
| Where a player beamed up from (their return point) | **That player**, player mod data | Per character, travels with the save |
| Zombie repulsion (shields) | **Each client**, for zombies it owns | Zombies are client-simulated |
| Phaser charge | **The carrying client** | Items in a player's own inventory |
| Helm, menus, map markers, notes | **Client** | Presentation only |
| Access rules | **Server**, sandbox options | Server owner decides |

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

Server -> client (`OnServerCommand` / direct in SP):

| Command | Client does |
|---|---|
| `landed {x,y,z}` / `landingRefused {why, blocked}` | Notes, and the beam-back if refused |
| `cabinReady` | Ends the arrival hold |
| `denied {why}` | Explains a refused request (access, transporter charge) |

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

- **Owner**: the first player to use the ship claims it -- on a hosted game
  that is naturally the host. Admins can reassign; the owner manages the crew
  list from the helm.
- With **Everyone**, ownership only decides who manages the crew list.

---

## Flight -- the decision

Hands-on flight as built **cannot be made correct**:

- It holds the pilot's body in mid-air, fighting the engine's fall simulation
  every tick; pilots took fatal damage in testing.
- It moves the body at 22-450 tiles/s. The speed anti-cheat flags anything
  over 20 tiles/s: on a default dedicated server the pilot is **kicked within
  seconds**.
- Its protection relied on role-gated calls that never worked.

Options:

| | What | MP-correct | Cost |
|---|---|---|---|
| **A** | **Travel from the helm only** (set a course on the map, take her down). Remove hands-on flight for now. | Yes -- no body movement, no strikes beyond the beam | Small; helm travel already works |
| **B** | Hands-on flight capped at ~15 tiles/s, body on the ground | No -- the body is still attackable, and 15 tiles/s is barely faster than driving | -- |
| **C** | **Vehicle flight**: the shuttle is a real vehicle, the pilot sits in a doorless seat (cannot be bitten), moved at up to the server's vehicle speed limit (70 tiles/s) | Probably -- uses the game's own vehicle sync and speed allowance | Large and unproven: custom vehicle script and model, and making a vehicle move freely over buildings is unexplored territory |

**Decision (2026-09-17): C -- the shuttle is a vehicle the crew enters like a
car.** The owner asked for exactly that, and the research backs it: entering a
vehicle is the game's own way to travel fast and safely in multiplayer.

- Entering a vehicle is not a teleport: no anti-cheat strike.
- An occupant may travel at the server's vehicle speed limit (default 70
  tiles/s), not the 20 tiles/s on foot.
- A seat with no door part cannot be bitten.
- Vehicle position is synced by the game itself.

Built in stages, each tested in game before the next:

1. **Shuttle vehicle.** A vehicle script for the shuttle with its hull model,
   doorless seats (pilot + crew), spawned by the server where the ship lands.
   The crew enters with the game's normal vehicle controls and can drive it
   on the ground. This alone replaces the unsafe hover and the speed kicks.
   *Verify:* a custom vehicle model loads (vanilla vehicle meshes are FBX; the
   hull is generated as `.x`), doorless seats cannot be bitten, it syncs on a
   dedicated server.
2. **Lift-off.** The pilot takes the vehicle up and flies it over buildings.
   Unproven: the driver's client must move the physics body itself, the
   engine re-enables physics and snaps vehicles to the floor, and vanilla
   never does it. If it cannot be made to work, stage 1 stands on its own.

The helm's flight-speed control and the photon torpedoes return with stage 2.
Until the vehicle exists, travel is by the helm (course + take her down) and
the old hands-on flight is removed.

This changes the hull: the landed ship **is** the vehicle, so landing, call
down, recall and the ghost-hull sweep move to spawning and removing a vehicle
on the server rather than a world item.

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

---

## Test plan

| Setup | How | Covers |
|---|---|---|
| Single player | Fresh world, *Water Shutoff: Instant* | Everything, one player |
| Dedicated server | Local test world with only the dev build enabled; host joins at 127.0.0.1 | Bounds, server build, streaming, charges, phaser |
| Two players | Second client (Steam Deck on LAN) on the dedicated server | Shared cabin, loot, shields, access |
| Hosted co-op | In-game Host (not reliable on the developer's PC; test when possible) | Same code as dedicated |

Static: every existing test, plus a protocol test that loads `server/` and
`client/` under lupa with the network stubbed and checks that every command a
client sends has a server handler that validates it, and that no client file
writes `TREK_Ship`.

---

## Migration order

Each step leaves single player working, is tested, and is committed.

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
9. **Tests and docs**: protocol test, DEV_GUIDE, README (server-owner notes).
