# Energy — everything aboard runs on the crystal

**Status: implementation guide. The design questions were settled with the
author on 2026-09-24 (section 13), and the whole guide is awaiting their
review. Nothing in it is built.** Once approved, it is followed phase by phase (section 12), and it
becomes the working guide for the ship's power in the shape `REPLICATOR.md`
and `PILOTING.md` use.

It is also `ROADMAP2.md` 1.6, the cold start: a dark ship is just the power
system at zero, so the cold start is the last phase of this guide rather than
a separate feature.

`DEV_GUIDE.md`'s *Rules that exist because they were broken* and
`MULTIPLAYER.md` still apply to every line of it: the server owns the reserve,
a client only asks, and nothing may depend on admin rights or `-debug`.

---

## 1. What the author asked for

In the author's words, condensed (2026-09-24):

- **Everything uses energy.** Calling the shuttle to you, starting her up,
  taking off, each beam in either direction, and driving — on the ground, and
  more in the air. The replicator and the EMH already charge; the EMH also
  costs a flat amount **to project him** (free to put away), so a dark ship
  says *"not enough energy to project the EMH"*.
- **Shields cost energy every time they repel a zombie**, and they also stop
  **crash damage**: while shields are up and there is energy, damage is
  repaired at once and paid for. Shields down, or no energy, and the damage
  stays.
- **The player can always see the power.** Notes like *"Energizing (25
  power)"* and *"Energizing... failed: not enough power"*, plus an on-screen
  gauge.
- **At zero power the ship goes dark.** Red emergency lighting. The
  replicator, the EMH, the sink and **every appliance** stop working.
- **Cold start (optional, the default for new worlds).** Zero energy, no spare
  crystals, two probes. The ship is **landed beside the first player**,
  undamaged and dark. She can't be driven or used to beam, so the player walks
  to the crystal the probe finds and walks back to load it into the core.
  Then the lights come on, with a very pleasant power-up sound. The tricorder
  in the sick-bay locker already finds crystals.

The four decisions taken in the same conversation:

| Question | Answer |
|---|---|
| Out of power with crew aboard or hovering | **No beaming.** As soon as there is room to land, she lands, with no damage. |
| The galley's fridge, oven and microwave | **Make them real powered appliances.** Today they are plain containers. |
| How power is shown | **An on-screen gauge plus notes.** The helm gets a bar as well. |
| Cold start default | **Cold start** for new worlds. Existing saves always migrate as commissioned. |

---

## 2. What exists today

Everything below was read from the tree on 2026-09-24. Line numbers drift, so
the function names are the stable part.

**The reserve** is `s.power` in ship state, `0..C.PowerMax` (5000, one
crystal). Spare crystals are `s.crystals`. `shared/TREK/TREK_Power.lua`:

- `P.reserve()`: a missing value reads as **full**, on purpose — a client
  hasn't been told yet.
- `P.crystals()`: a missing value reads as **none**.
- `P.afford(cost)`: authority only. It may burn a spare to cover the cost.
- `P.spend(n)`: authority only. It clamps at 0. The caller commits.
- `P.burnCrystal()`: **sets** the reserve to full. Whatever was left in the
  old crystal is lost.

**What charges today:** replication (4–150, `atReplicator` / `replicate` in
`TREK_Server.lua`), an EMH treatment (25, `spendTreatment`), and probe
fabrication (250, `buildProbe`). The EMH cure takes a whole spare crystal and
never touches the reserve. A probe *launch* spends a probe from the rack, not
energy.

**The refusal protocol.** The server calls `deny(player, why, extra)` and sends
`denied`. The client looks the reason up in the `DENIALS` table in
`client/TREK/TREK_Core.lua`, with special branches for reasons that carry
numbers (`recharging`, `repNoCrystal`). `tests/test_multiplayer.py` fails if a
`deny()` literal has no `DENIALS` entry. Notes go through `U.note(player, text,
r,g,b)`: red is a refusal, orange a warning, blue information.

**What this guide has to change, and why:**

- **Nothing about movement costs energy.** Beams spend a *transporter charge*
  (the anti-cheat limiter, `MOVES` in `TREK_Server.lua`). That is a different
  thing and stays as it is.
- **She has no start-up step.** `prepareVehicle` repairs and hotwires her at
  spawn, and `S.refuel` tops the `GasTank` part up whenever it falls below
  half, every service pass (60 ticks). Her `Battery` part is never touched.
  Driving is vanilla's job.
- **The server doesn't know her speed**, and runs no vehicle physics. It does
  see her position change: `serviceVehicle` syncs `s.x/s.y` from the vehicle
  once every 60 ticks and commits when they change. That delta is the
  odometer.
- **Shields push zombies on each client** (`Core.repelZombies`, every 20
  player updates, local zombies only). The function counts `pushed` and
  nobody reads it. The server never hears about a push.
- **Nothing repairs crash damage.** The only `repair()` is at spawn.
- **The EMH is free to summon** (`emhSummon` / `emhDismiss`, `B.serviceEMH`).
- **The cabin lights can't be changed.** `lightCabin()` calls
  `cell:addLamppost` for the two deckhead lamps and the pad, **throws away the
  handles**, and sets a `lit` flag. It also still calls
  `setHaveElectricity(true)`, which DEV_GUIDE records as a no-op. The EMH's
  light keeps its handle and shows how removal works.
- **The television is the only real device.** It is powered by the
  battery-branch trick in `TREK_Power.serviceDevices`, in every process.
- **The fridge, oven and microwave aren't appliances.** They are plain
  `IsoObject.new` containers — drawn, openable, and inert (DEV_GUIDE: a stove
  built that way "is drawn and cannot be used"). Section 9 is what making
  them real takes.
- **The sink** is refilled every game minute by `B.refillWater` and costs
  nothing.
- **A new world starts commissioned:** full reserve, three spares
  (`furnishCore`, `C.DilithiumIssue`), no probes, and the ship **overhead**.
  The first player beams up from anywhere.
- **Two hooks already wait for this guide:** `M.hearing()` in
  `TREK_Missions.lua` ("the one line cold start changes") and `S.commission()`
  in `TREK_CommsServer.lua` (committed in 1.6.0, `COMMS.md` 9). Today the
  comms work treats "commissioned" as "first boarded" and sets `d.day0`.

---

## 3. The model

### 3.1 One ledger, one function

Every charge goes through **one server function**, so no consumer can charge
twice, forget to commit, or refuse with its own wording:

```lua
-- server/TREK/TREK_Server.lua (or a new server/TREK/TREK_Energy.lua)
--- Pays `cost` from the reserve for `what`, or refuses. Authority only.
--- Returns true when paid. Commits. Tells the asker either way.
function S.energize(player, what, cost, opts)
```

- `P.afford(cost)` then `P.spend(cost)`, then `Ship.commit()`, then
  `Net.toClient(player, "energized", {what, cost, left})`, which the client
  shows as **"Energizing (25 power)"**.
- If it can't pay: `deny(player, "noPower", {what, need = cost, have =
  reserve, kind = opts.kind})`, shown as **"Energizing... failed: not enough
  power (25 needed, 3 left)"**. `kind` clears a waiting move on the client,
  the way `recharging` does.
- `opts.silent` is for the continuous drains (driving, hovering, shields,
  repair). They would spam a note every second. They report through the
  gauge and the threshold warnings (3.4) instead.
- `opts.partial` is also for the continuous drains: pay what there is, then go
  dark. A shield that has half a push's worth left still pushes.

**The existing charges move onto it.** `spendTreatment`, `buildProbe` and
`replicate` become callers. `repNoCrystal`, `emhNoPower` and `probeNoPower`
stay as the `what` part of their messages, so their tests stay meaningful. The
`probeNoPower` handler that DEV_GUIDE's reader noticed never shows its numbers
is fixed along the way.

### 3.2 Dark is a state, not a number

```lua
--- True when the ship has no power at all: less than one unit left and no
--- spare to burn. Shared, so every client can render it.
function P.dark()
```

It is **published as `s.dark`** as well as derivable, for three reasons:

- a transition must fire exactly once (3.3);
- a client whose copy has no `power` yet reads the reserve as full, and a
  published flag is unambiguous;
- the cold start begins dark by *decision*, not by arithmetic.

`ROADMAP2.md` says *never infer a campaign from a low reserve*, and this is how
that is kept.

**Every consumer checks dark first**, on both sides. The client greys or
refuses without a round trip; the server refuses authoritatively.

**What still works when dark:**

- the hatch (walking);
- the sensor console, and **launching a probe already in the rack**;
- the warp core's *Load a crystal*;
- the tricorders and the medical set (their own items);
- opening lockers and containers;
- reading the gauge;
- **the PADD and the Adirondack channel** (decided 2026-09-24: a PADD has its
  own battery and talks to orbit directly). Calls ring, hails are answered and
  tapes are read off a PADD in a dark ship exactly as in a lit one; a missed
  call comes back worse whatever the power was, so an outage never loses the
  story. Tapes the channel issues are still delivered to the shelf -- a shelf
  is not an appliance.

Everything else is refused with the same "not enough power" note.

### 3.3 Going dark, coming back

`S.powerChanged()` runs after every spend and every crystal load. It compares
`s.dark` with `P.dark()` and, on a change, commits and broadcasts once:

- **`powerDown`**: *"Main power lost -- emergency lighting"* (orange). The
  cabin goes red (section 8), and a hovering ship begins an emergency landing
  (section 7).
- **`powerUp`**: *"Main power online"* (blue), the power-up sound, and the
  lights come back to white.

**Loading a crystal into a dark ship burns it at once.** Today *Load a
crystal* only adds a spare, and a spare is burned lazily by the next `afford`.
A dark ship has to come back on the moment the crystal goes in, because that
is the payoff the cold start is built around. `loadCrystal` therefore calls
`P.burnCrystal()` when the ship is dark, then `S.powerChanged()`.

### 3.4 The readout

**The gauge** (new: `client/TREK/TREK_PowerHUD.lua`) is a small LCARS bar in a
screen corner.

- It is shown **while aboard, or seated in her**. That means `U.isAboard` or
  the local player's vehicle is the shuttle.
- It uses the helm's own palette and helpers (`H.P`, `H.pill`).
- It shows the reserve as a bar and a number, and the spares as pips.
- The bar turns amber at 25% and red at 10%.
- When dark it reads **EMERGENCY POWER**, blinking slowly.
- It isn't interactive, so it takes no controller focus. DEV_GUIDE's
  *Every panel must work with a controller* is met by never focusing it.
- It redraws on `Ship.onChange` and never polls.

**The helm** gets the same bar (it has no power readout today), drawn with the
replicator's code: `TREKReplicatorWindow:render` already has one, and the bar
is lifted into `TREK_Helm.lua`'s helpers so all four panels share it.

**Threshold warnings** go to the crew, once each, on the way down: 25%, 10%,
and "last crystal burning" when a spare is burned and none is left.

### 3.5 Costs

Every number is a `C.*` constant in `TREK_Config.lua`, and each carries a
comment saying where it came from. These are **starting values, meant to be
tuned in play.**

| What | Constant | Cost | When it is charged |
|---|---|---|---|
| Beam, per person, either direction | `C.BeamCost` | 25 | `move` handler, kinds `beamUp` / `beamDown` (including *Forward to the cockpit*) |
| Call her down | `C.LandCost` | 150 | `land` success, and the helm's *take her down* |
| Send her up | `C.RecallCost` | 50 | `recall` success, including the automatic climb when the last crew member beams down |
| Start her up | `C.EngineStartCost` | 25 | the engine starting (4.2) |
| Take off | `C.TakeoffCost` | 100 | checked at `takeoff`, spent at `airborne` |
| Driving on the ground | `C.GroundCostPerTile` | 0.5 / tile | `serviceVehicle`, silent |
| Moving in the air | `C.AirCostPerTile` | 2 / tile | `serviceVehicle`, silent |
| Hovering | `C.HoverCostPerMinute` | 1 / game minute airborne | `EveryOneMinute`, silent |
| Shield repel | `C.ShieldPushCost` | 2 / zombie | client report (5.1), silent |
| Crash repair | `C.RepairCostPerPoint` | 1 / condition point | `serviceVehicle` (5.2), silent |
| Project the EMH | `C.EmhProjectCost` | 100 | `emhSummon`; dismissing him is free |
| EMH treatment | `C.EmhTreatCost` | 25 | unchanged |
| Replication | existing | 4–150 | unchanged |
| Fabricate a probe | `C.ProbeCost` | 250 | unchanged |
| Galley appliances | `C.ApplianceCost...` | to be decided in section 9 | per game hour of draw, silent |

**Free, deliberately:**

- **The hatch.** It's a door, and it is how a dark crew gets out.
- **`recover`**, the beam home when a landing search gives up. It is a
  failure path, and DEV_GUIDE's *Never let a failure strand the player*
  outranks the economy.
- **The emergency landing** (section 7).
- **Launching a probe**, which was paid for when it was fabricated.
- **Lights, sink and television while powered.** They are what going dark
  takes away. Charging for them would be a steady drain nobody can see a
  reason for.

**What a crystal buys: about three outings (the author's choice,
2026-09-24).** A crystal is 5,000 units, and the ship burns one at a time. An
*outing* is one typical session with the ship:

| Part of an outing | Units |
|---|---|
| Call her down | 150 |
| Take off | 100 |
| Fly about 500 tiles (2 / tile) | 1,000 |
| Hover an hour of game time (1 / minute) | 60 |
| Shields push about 50 zombies (2 each) | 100 |
| One scrape repaired | 100 |
| Four beams (25 each) | 100 |
| Summon the EMH and one treatment (100 + 25) | 125 |
| **Total** | **about 1,800** |

5,000 / 1,800 is **about three outings per crystal**. The player sees the gauge
fall, and a crystal hunt comes round every few sessions. Before this guide,
only the replicator drew power, so a crystal almost never ran out.

**Flight is more than half of every outing**, so it is the lever when tuning:

- about one outing per crystal is roughly double these prices (flight about
  4 / tile);
- about ten is roughly a third (flight about 0.6 / tile).

The test in `test_multiplayer.py` that prices this outing and asserts it
lands between 1,500 and 2,100 is what keeps a later tweak from quietly
changing the feel.

### 3.6 Commits

The reserve is ship state, and ship state is transmitted whole on every commit
(DEV_GUIDE: *State that is transmitted whole cannot hold a list that grows*).
A number costs nothing to carry, but **how often** matters:

- driving already commits whenever she moves a tile, so the drain rides that
  commit;
- hovering is once a game minute;
- shield reports are batched to one every five seconds per client, at most;
- repair runs with the vehicle pass.

No drain may add a commit per tick.

---

## 4. Movement

### 4.1 Transporter and calling her

- **Beams:** `Net.onServer("move")` in `TREK_Server.lua`. The energy check
  goes **after** the transporter-charge check, so a refusal for charges
  doesn't cost energy. It goes **before** `moveGranted`, with `kind` in the
  denial so the client drops the waiting move. `hatchIn`, `hatchOut` and
  `recover` pass without a charge.
- **Call her down:** the `land` handler charges after `S.land` succeeds. A
  landing that is refused costs nothing.
  - The client pre-check in `M.onCallDown` refuses early when dark or short.
  - `descend` (the helm's take-her-down) runs a move and then a land. It is
    checked at the move for the landing cost and charged once, at the land.
- **Send her up:** `S.recall`. When dark she can't go up. A landed dark ship
  stays landed, and the refusal says why.

### 4.2 Starting up, and running out on the ground

**The vehicle's own parts are the gate, because the engine already obeys
them:**

- **`Battery` charge.** `BaseVehicle` has `engineDoStartingFailedNoPower`.
  Vanilla fails an ignition on a flat battery, with its own message and
  sound. The server keeps the battery **full while powered and flat when
  dark.** That is the "can't start her" of a dark ship, with nothing of ours
  in the ignition path.
- **`GasTank`.** `S.refuel` stops topping up while dark, and **empties the
  tank** on `powerDown`. An engine that is running stalls, which is vanilla's
  behaviour at an empty tank.
- **The start-up charge.** `serviceVehicle` watches `isEngineRunning()` on the
  server's copy. On a false→true edge it charges `C.EngineStartCost` to the
  driver, with the "Energizing (25 power)" note. If it can't pay, the ship is
  dark by definition, and the battery and tank above have already refused.

**Verify first (V3):**

- that a flat battery really refuses the start on a client in multiplayer;
- that the server's copy sees the engine state;
- that `transmitPartModData` / `transmitPartCondition` carry the battery
  charge.

If the battery isn't honoured, the gas tank alone still gates driving, and
start-up becomes the first tile's charge.

### 4.3 Driving and flying

`serviceVehicle` already compares her position against `s.x/s.y`. The
distance between the old and new position is the odometer:

- `C.AirCostPerTile` while `s.flying`, otherwise `C.GroundCostPerTile`;
- the spend is added to the commit that pass already makes;
- `opts.partial` pays the remainder and goes dark.
- **A jump is not a journey.** A delta larger than `C.OdometerMaxJump` (a
  respawn, a landing move, a teleport) is ignored rather than billed.

Hovering charges `C.HoverCostPerMinute` from `EveryOneMinute` while
`s.flying`, whether or not she moves. Holding five tonnes up isn't free.

### 4.4 Take-off

`takeoff` refuses early when dark, or when `C.TakeoffCost` can't be afforded.
The cost is **spent at `airborne`**, when she is actually up, so a climb that
gives up (PILOTING.md 2.x) costs nothing.

If the reserve went dark between the two, she is airborne and dark. That is
section 7's case, and it is handled there.

---

## 5. Shields

The shield toggle (`s.shields`, `setShields`) is unchanged. What changes is
that **the shields do two jobs and both are paid for**, and **the shields do
nothing at all while dark**. The gate is `U.shieldsUp() and not P.dark()`,
used everywhere.

### 5.1 Repelling zombies

`Core.repelZombies()` already returns `pushed`. The client adds it to a
counter. At most every `C.ShieldReportSecs` (5 s), a non-zero counter is sent
as `shieldDraw {n}`, and the server charges `n * C.ShieldPushCost` with
`partial` and `silent`.

- **Which client:** every client that simulates zombies near the hull. That is
  the existing design (`MULTIPLAYER.md`: each client pushes its own), and each
  pays for its own.
- **The honest limit:** the count comes from the client. A modified client
  could under-report and get cheaper shields on a shared ship. The server
  can't count pushes it doesn't perform, and moving zombies on the server
  doesn't work, because clients own them. This is accepted and written down,
  not fixed. The worst case is that one cheater's shields cost the ship less.
- **Dark:** the repel gate reads `P.dark()`, so a dark ship's clients stop
  pushing on the next publish, with nothing more to send.
- **Sim hole to close:** nothing in `pz_sim.lua` counts pushes today, because
  nothing reads the count. The test has to put real zombies in the field and
  assert the charge, **before** the report batching can hide a zero.

### 5.2 Crash damage

While `U.shieldsUp() and not P.dark()`, `serviceVehicle` walks her parts
(`getPartCount` / `getPartByIndex`). For each part below its maximum
condition:

- it restores the condition with `part:setCondition(max)`;
- it transmits with `vehicle:transmitPartCondition(part)` (vanilla's server
  call: `server/Vehicles/VehicleCommands.lua`);
- it charges `C.RepairCostPerPoint` per point restored, `partial`, `silent`.

The `GasTank` and `Battery` are skipped: those are power, not damage.

- **"Instantly"** means within one vehicle pass, a second. If play shows a
  visible dent-and-mend, the repair gets its own 10-tick check while she is
  moving.
- **Shields down, or dark:** the damage stays, and vanilla's own mechanics
  apply — the shuttle becomes an ordinary damaged vehicle.
- **Verify first (V4):**
  - **which machine applies collision damage** in multiplayer (the physics
    owner, and does the server's copy see it?);
  - whether `frontEndHealth` / `rearEndHealth` in the vehicle script are
    part conditions or a separate body health with its own setter;
  - whether `setCondition` on the server reaches the driver's copy before
    their next collision overwrites it.

  The answer decides whether repair runs on the server (preferred) or has to
  be requested by the driver's client.

---

## 6. The EMH and the replicator

- **Projecting the EMH costs `C.EmhProjectCost`**, charged in `emhSummon`.
  `E.refusal` gains the dark case, so the menu is greyed and the panel says
  **"Not enough power to project the EMH"**. Dismissing him stays free and
  stays reachable when dark (it already skips `atEMH`).
- **Going dark takes him away.** `powerDown` sets `s.emh = nil` and runs
  `B.serviceEMH()`. The projection needs power to exist at all.
  - **A cure that is running fails** (the author's decision, 2026-09-24:
    *"PZ is a fiercely realistic simulator"*). The twelve hours aboard are
    the Doctor keeping the patient under treatment. If the ship goes dark
    during them, the treatment stops:
    - the patient **stays infected**;
    - the crystal that paid for the cure is **gone**, with no refund;
    - the crew are told plainly: *"Main power lost -- the Doctor's treatment
      has failed. You are still infected."* (red). It has to be delivered,
      because a cure that ends in silence reads as a bug. DEV_GUIDE: *a
      correct refusal that nobody is shown is indistinguishable from a broken
      feature*.

    `S.beginCure`'s running state is cleared on `powerDown` by the same code
    that already ends a cure that fails its conditions. The test starts a
    cure, drains the ship to dark partway through, and asserts all of it: the
    bite and the infection still present, `s.crystals` not refunded, the cure
    state gone, and the message sent. The cure is paid for with a *spare*
    crystal, so the one burning in the core is a separate thing. It is
    possible to pay for a cure and then run the reserve dry with the
    replicator, and that is the case the test uses.
- **The replicator** already refuses when it can't afford. It gains the dark
  gate so its panel reads **OFFLINE**, instead of offering buttons that all
  fail.

---

## 7. Emergency landing — the author's rule

> *"With no power the fallback is no beaming, but as soon as there is room to
> land, it lands with no damage."*

**The engine constraint:** ground is only loaded around a player, and the
server builds only where a player is standing (DEV_GUIDE: *Never build where
no player is standing*). So an emergency landing has to happen **where the
crew are**. Each case below follows from that.

**7.1 Hovering, with a pilot in the seat.** On `powerDown` the server sends
`emergency` to the pilot's machine, which owns her physics.

- The pilot's client **keeps the engine alive at a capped speed**
  (`C.EmergencyGlideSpeed`). Her tank is exempt from the dark-empties rule
  while `s.emergency` is set, and nothing is charged.
- **She sets down at the first moment her footprint below is clear**: the
  pilot's flight tick runs `W.roomToLand` under her each pass and starts the
  existing descent move (`F.land`'s path, without the pilot's command).
- **No damage.** It is the ordinary touchdown move, not a fall. The repair in
  5.2 is dark and can't help, so the landing itself must be soft, and the
  test asserts the part conditions are unchanged.
- The pilot can steer toward clear ground in the meantime. That is the whole
  of their control.

**7.2 Hovering with nobody in the seat** (the crew are in the cabin, or
walked away). There is no physics owner, so the server does what `S.endFlight`
already does for an empty ship, but downwards:

- it searches for the nearest clear footprint around her (the sliced
  `W.searchSlice`, out to `C.LandingSearchRadius`, **only while her ground is
  loaded**);
- it removes the flying vehicle and spawns her on the ground there, through
  `S.land`'s own path. That is a clean spawn, `repair()` included, so there
  is no damage.
- If nothing is clear, she holds and the search retries every pass. If her
  ground isn't loaded, nobody is near her, and she waits for them.

**7.3 In orbit, with crew in the cabin.** A ship overhead can only go dark by
spending from the cabin (the replicator, the Doctor, a probe fabricated). With
no power, the crew can't beam down, and a hatch has nothing to open onto.

So a dark ship in orbit **takes herself down**. It is the helm's own *take her
down* (`T.descend`), run for the first crew member aboard, to their return
point:

- it is free;
- it is announced as *"Main power lost -- emergency landing"*;
- the landing site search is the one the helm already uses.

This is a **landing** in the story and in the code: the crew arrive standing
beside her with the hatch in front of them. It is the same move `descend`
makes today, and not a transporter beam.

- **Approved by the author, 2026-09-24.** It is the one place the ship moves
  the crew without being asked, and the only way the engine allows her to
  land where nobody is standing.
- The rejected alternative was refusing any cabin spend that would take a
  ship in orbit below `C.LandCost` ("power reserved for landing").

**7.4 After touchdown** she is an ordinary dark ship on the ground: landed,
battery flat, tank empty, hatch working. `s.emergency` clears.

---

## 8. The dark cabin

**8.1 Lighting.** `lightCabin()` is rewritten to **keep every `addLamppost`
handle** (the EMH light's pattern) and to take two looks:

- **Powered**: the current white deckheads (0.92, 0.96, 1.0, radius 8) and the
  blue pad light.
- **Dark**: two red emergency lamps, `C.EmergencyLight` (about 0.85, 0.10,
  0.08, radius 5). The pad light is off.

A lamppost can't be recoloured in place, so a change **removes and re-adds**.
It happens on `Ship.onChange` when `s.dark` flips, never per frame. There is no
pulsing: a pulse would be a remove-and-add every few ticks, which is
thrashing the light grid for decoration.

The dead `setHaveElectricity(true)` loop in `lightCabin` is deleted, per
DEV_GUIDE.

**8.2 The television.** `P.serviceDevices` skips the top-up when dark and sets
the device's power to 0. The engine then switches it off by itself (the
battery branch in the `TREK_Power.lua` header), and it can't be switched back
on until power returns. This runs in every process, exactly as the top-up
does today.

**8.3 The sink.** `B.refillWater` stops refilling when dark and **empties the
fixture's store**: the pumps are off and there is no pressure. When power
returns, it refills within a game minute, as it does today.

**8.4 The replicator, the EMH and the galley** are in sections 6 and 9.

**8.5 The sounds.** `tools/gen_power.py` is new, in the house style
(`gen_medical.py`'s `write()`, Python `wave`, 44.1 kHz, 16-bit mono):

- **`TREK_PowerUp`** — the one the author asked to be super pleasant. About
  3.5 s:
  - a low warp-core hum swelling up from nothing;
  - a slow rising sweep over it;
  - a three-note major chime as the lights come on, landing on a warm
    sustained chord that fades into the core's idle hum.
  - Rendered, then vetted by listening, the way the icons are vetted by
    looking.
- **`TREK_PowerDown`** — a short falling whine and a thud. Deliberately
  unpleasant, and about a second long.

Both are declared in `scripts/trekshuttle.txt` (non-3D, `category = Item`) and
added to `tools/deploy_windows.py`'s explicit wav list.
`tests/test_assets.py` already fails on an undeclared sound.

---

## 9. The galley made real

**The author chose this, and it is the largest unknown in the guide**, so it
opens with research. The first finding is already in:

```
ItemContainer.isObjectPowered(obj, _)            (javadis, 2026-09-24)
  103  obj:getSquare()
  119  IsoGridSquare.haveElectricity()   -- a running generator in the chunk
  127  IsoGridSquare.hasGridPower()      -- the town mains
```

A fridge cools when `isPowered()`, and powered means **a generator or the
grid**. The television's battery trick doesn't apply: a fridge isn't a
device. There is no Lua setter for "this square has power"; DEV_GUIDE already
records that `setHaveElectricity` sets nothing.

**So the engine-native route is a generator the player never sees**: an
`IsoGenerator` in the cabin's chunk, standing in for the warp core's power
bus.

- Its fuel is kept full from the reserve, and it is `setActivated(false)` on
  `powerDown`.
- Every vanilla appliance in range then works with vanilla's own code: the
  fridge cools, the oven and microwave heat, and nothing of ours is in the
  food path.
- The draw is billed honestly: each game hour, the fuel the generator burned
  (`getTotalPowerUsing`) is converted at `C.FuelToEnergy` and charged, then
  the tank is refilled.
- The oven and microwave must also be **built as `IsoStove`**
  (`IsoStove.new(cell, sq, sprite)`). That is the television lesson
  (DEV_GUIDE: *A sprite is not the object the engine builds from it*).

**What has to be proven before a line of it (V5–V8):**

- **V5.** An `IsoGenerator` can be made from Lua on the server and
  transmitted: `IsoGenerator.new(item, cell, sq)`. Its only vanilla call site
  is `client/Tests/TimedActionsTests.lua`, which is a test file. By
  DEV_GUIDE's own rule that proves nothing, so the server-side route vanilla
  uses when a player places a generator has to be found and read.
- **V6.** It powers squares with **no building**, at the cabin's z
  (`isPoweringSquare`, `getMin/MaxAffectedLevel`). *A runtime-generated
  interior is not a building* has bitten this mod before.
- **V7.** It can be **hidden and made untouchable**:
  - which sprite it draws, and whether that can be empty;
  - where it stands. A square in the hull ring outside `C.inShape` can't be
    walked to, but a right-click can still resolve to it.
  - `OnFillWorldObjectContextMenu` must strip vanilla's *Take generator*,
    *Turn on/off*, *Add fuel* and *Fix*;
  - it must not wear out: `setCondition` is kept full;
  - its hum and noise must be acceptable. The cabin is in the void and there
    is nothing out there to attract.
- **V8.** A fridge built at runtime from a fridge sprite gets a container of
  type `fridge` and **cools** under that generator. An `IsoStove` built at
  runtime heats. And the fridge's contents survive the rebuild that turns the
  old `IsoObject` into the new class. This is the `refitCabin` lesson: hand
  the live items back, never recreate them from their types.

**If V5–V7 fail**, there is no second engine route for cooling: the fridge's
power check reads only the generator and the grid. The phase then stops and
reports back, and the galley stays shelves. It is ordered **after** the rest
of the system (section 12), so a failure here doesn't hold anything else up.

**If it works, it is a `C.BuildRev` bump**: new object classes on existing
squares. The rebuild has to move the fridge's and oven's contents across, and
`tests/test_layout.py` has to learn the new fittings.

---

## 10. Cold start

### 10.1 The option

It is a new sandbox option, `TrekShuttle.StartState`, following the existing
pattern (`sandbox-options.txt`, `Sandbox.json`, a reader in `TREK_Power.lua`,
and `C.StartCold = 1` / `C.StartCommissioned = 2`):

- **Cold start** (1, the default): earn the first crystal.
- **Commissioned** (2): the ship as she is today.

An absent value reads as **cold**, which is the feature as designed
(`C.ReplicatorPatterns` sets the precedent). It only matters on a brand-new
ship, because of 10.4.

### 10.2 The state

```
s.commissioned  = false      -- explicit, published; never inferred from power
s.coldStart     = true
s.power         = 0
s.crystals      = 0          -- furnishCore must not issue C.DilithiumIssue
s.probes        = C.ColdStartProbes   -- 2
s.dark          = true
```

`U.state()`'s "a missing power is full" default must **not** fire for a cold
ship. The cold state is written once, by the server, when the ship is created.
The first read never fills it in. `furnishCore`'s `if s.crystals == nil`
already stands aside for an explicit 0.

### 10.3 Where she is

**Landed beside the first player, not overhead.** A dark ship overhead could
never be reached.

- The server waits for the first player to be in the world, alive and on the
  ground, with their chunks loaded. It never builds where nobody stands.
- It runs the sliced landing search around them, preferring **6 to 15 tiles
  away**: close enough to see, with room to walk to her. It excludes their own
  square (`W.exemptFor`).
- It lands her with `S.land`. That is a clean spawn, so she is undamaged, with
  her battery flat and tank empty (4.2).
- *"Your shuttle is down nearby, without power"* (blue), to that player. On a
  server, the first player means the first to join. Everybody else finds her
  where she is.
- If there is no room within the radius, it retries as the player moves.
  `s.coldPlaced` records success, so it never happens twice.

### 10.4 Commissioning

The first `powerUp` of a cold ship is the commissioning:

- `s.commissioned = true`, and `powerUp` carries `first = true`;
- the note is **"The shuttle is commissioned -- main power online"**, with the
  same sound and lights;
- `M.hearing()` becomes `s.commissioned == true`, which is the one line
  `TREK_Missions.lua` was left waiting for;
- `S.commission()` in `TREK_CommsServer.lua` sets `d.day0` on
  `s.commissioned`, not on `s.built` -- one condition. The comms work has
  landed (1.6.0), so there is nothing left to collide with. **The sandbox's
  *When the Adirondack first calls* then counts from the first power-up** on
  a cold ship: "straight away" means straight after commissioning (decided
  2026-09-24). A commissioned start keeps first boarding as day zero, as
  today.

**Existing saves migrate as commissioned.** In `OnInitGlobalModData`, a ship
with no `s.commissioned` field that has ever been built or landed gets
`s.commissioned = true`, whatever the sandbox says. A save is never drained. A
save whose ship has never existed at all is treated as new.

### 10.5 The loop the player plays

Nothing in this list needs new code beyond sections 3–10.4. That is the point
of building the power system first.

1. They spawn and are told the shuttle is down nearby.
2. They walk to her and in through the hatch (free). The cabin builds on
   arrival, as it always has. It is red-lit and silent. The gauge reads
   EMERGENCY POWER.
3. They open the sensor console and launch one of the two probes. **The first
   probe of a save always finds something** (`s.probeEverFound`, already
   built).
4. The report marks a dilithium contact on the map.
5. They take the tricorder from the sick-bay locker, walk out through the
   hatch, and walk to the contact.
6. The crystal is placed when they load its ground (deferred placement,
   already built). They find it with the tricorder and pick it up.
7. They walk back, go in through the hatch, and *Load a crystal* at the core.
   It burns at once (3.3).
8. The power-up sound, white light, and "The shuttle is commissioned".
   Everything unlocks, and the comms clock starts.

### 10.6 Soft-lock prevention

`ROADMAP2.md` lists the ways the campaign has to survive. Each one is answered:

| Case | Answer |
|---|---|
| Both probes find nothing | Can't happen to the first, by design. The second is an honest search. |
| The crystal's contact expires (no ground to place on) | **Recovery probe**, below |
| Probes gone, no crystal anywhere they know of | **Recovery probe**, below |
| The crystal is lost after pick-up (death, dropped in a river) | Crystals are in twelve vanilla loot tables, and the tricorder plots them. Plus the recovery probe. |
| Player dies | The ship, her state and the contacts are the server's, and a new character finds her where she is. |
| Server restart | All of it is ship state or the contact store, persisted. |
| Ownership changes | Access rules are unchanged. The hatch still needs `mayUse`. |
| Modded map with no loot tables | The probe route never needed them. |

**The recovery probe:** once a game day, the server checks a cold,
uncommissioned ship. If it has no probes in the rack, no probe in flight, no
unrecovered dilithium contact, and no crystal in the core, it puts **one**
probe in the rack (`s.coldRecoveries` counts them, for the log). A WARN is
logged if that ever happens more than three times in a save, because that
would be a bug, not bad luck.

---

## 11. Multiplayer

The whole guide follows the existing rules. The points specific to energy:

- **One reserve, one ledger, on the server.** Every charge is
  `S.energize`, called inside a handler that has already validated access and
  position. Two players racing a beam or a replication each pay once, or one
  is refused. `test_multiplayer.py` asserts both.
- **Clients render `s.dark`, and never compute a gate that the server doesn't
  also enforce.**
- **Per-process work stays per-process:** the lights, the television's power
  value and the shields' pushes, as today.
- **The only new client-to-server traffic** is `shieldDraw` (batched) and the
  engine-start edge, if V3 says the server can't see it for itself.
- **The only new server-to-client traffic** is `energized`, `noPower` (via
  `denied`), `powerUp`, `powerDown`, `emergency` and the threshold warnings.

---

## 12. Order of work

Each phase ends with the static checks green, a mutation pass on what it
added (DEV_GUIDE's practice: one mutation at a time, asserting it applied),
and a commit. None of it needs a game until the phase marked **play**.

| # | Phase | Delivers |
|---|---|---|
| 0 | **Verify first** | V1–V4 below, answered from bytecode and vanilla Lua, written into this file. |
| 1 | **The ledger** | `S.energize`, `P.dark`, `s.dark`, `powerUp`/`powerDown`, the notes, the `DENIALS` entries, the three existing charges moved onto it, burn-on-load when dark. |
| 2 | **The gauge** | `TREK_PowerHUD.lua`, the shared bar, the helm's bar, threshold warnings. UI harness tests. |
| 3 | **Movement** | beams, call-down, recall, take-off, the odometer, hover drain, battery and tank gating, the engine-start charge. |
| 4 | **The dark cabin** | light handles and red emergency lighting, television off, sink off, replicator offline, EMH projection cost and dark removal, a running cure failing when dark (patient still infected, crystal lost), `gen_power.py` and both sounds. |
| 5 | **Shields** | repel reports and charges, crash repair. |
| 6 | **Emergency landing** | 7.1–7.4, with the sim made unkind enough to test a dark hover (a pilot, no pilot, blocked ground, unloaded ground). |
| — | **Play** | One single-player session: spend to dark, see the red, load a crystal, hear the sound. Hover to dark over a town. This is the first time anything here is proven. |
| 7 | **Cold start** | the option, the cold state, placement beside the first player, commissioning, the migration, the recovery probe, `M.hearing`. Then the comms hook, once the other session's work has landed. |
| — | **Play** | A fresh cold world, walked end to end (10.5). |
| 8 | **The galley** | V5–V8, then the hidden generator, the `IsoStove`s and the `BuildRev` bump. It stops and reports if V5–V7 fail. |
| 9 | **Docs** | This file rewritten as a working guide. `ROADMAP2.md` 1.6 marked built. DEV_GUIDE's *Current state*, the README's known limits, `MULTIPLAYER.md`'s traffic list, `PILOTING.md` (emergency landing), `EMH.md` and `REPLICATOR.md` (their dark behaviour). **Version 1.7.0** -- 1.6.0 is the PADD and the channel. |

### Verify first

- **V1.** `P.afford` burns a spare *before* a cost it can cover. With many
  small drains the reserve reaches 0 exactly, and the next half-unit burns a
  crystal, losing nothing. Confirm with numbers that `partial` + burn never
  loses more than one unit per crystal. DEV_GUIDE: *A branch a mutation cannot
  break may be unreachable* — look at the numbers.
- **V2.** Where `addLamppost` lights are drawn for a player standing in the
  cabin, and whether `removeLamppost` on the handle takes effect in the same
  frame (the EMH light suggests yes).
- **V3.** Battery, tank and engine state (4.2): flat battery refuses ignition,
  the server sees `isEngineRunning`, and the part syncs reach the driver.
- **V4.** Crash damage (5.2): which machine applies it, what front and rear
  health are, and whether a server-side `setCondition` sticks.
- **V5–V8.** The galley (section 9), done at the start of phase 8, not now.

**Already true, and worth knowing before phase 7:** holo-fragment clue sites
only appear after first contact (`S.clueFor` waits on the channel's `met`
flag), and first contact waits on day zero -- so on a cold ship the two opening
probes can only ever find dilithium. Nothing needs adding for that.

### Sim holes to expect

This list comes from DEV_GUIDE's *The simulation has to be as unkind as the
engine*. `pz_sim.lua` has none of the following today, and each one is a way
for a test here to pass for the wrong reason:

- vehicle part conditions that go down in a collision;
- a battery charge the ignition reads;
- an engine state with a start edge;
- zombie pushes that are counted;
- lamppost handles that can be removed;
- a sink store that can be emptied;
- a generator.

Each gets modelled **before** the test that relies on it.

---

## 13. Decisions settled with the author (2026-09-24)

1. **The emergency descent from orbit** (7.3): yes.
2. **Costs** (3.5): **about three outings per crystal**, at the prices in the
   table, tuned in play from there.
3. **Hovering costs power** even when she is standing still: yes.
4. **A running EMH cure fails if the ship goes dark** (section 6). The patient
   stays infected and the crystal is lost. *"PZ is a fiercely realistic
   simulator."*
5. **Lights, sink and television are free while powered**: yes. The galley
   appliances draw power through the generator (section 9).
6. **Cold-start placement**, 6 to 15 tiles from the first player (10.3): yes,
   as a starting distance.

What is still open is the verify-first list (section 12). Those questions are
answered by the engine, not by the author.
