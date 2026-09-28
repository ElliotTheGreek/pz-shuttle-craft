# Boarding clearance: earning the Adirondack

The working guide for how a player earns their way aboard the U.S.S.
*Adirondack*, in the shape `ENSIGN.md` and `EMH.md` use: what the player does,
what happens, the numbers, where things live, the engine facts not to
re-derive, and what will bite you.

Until this, the shuttle's aboard menu offered *Beam to the U.S.S. Adirondack*
from the first minute. Now, under the sandbox's default, it has to be earned,
and the earning is the story's spine between the first rescue and the bridge.

Almost nothing here is a new mechanism. It is the rescues (`ENSIGN.md`), the
contact store and probes (`PROBES.md`), deferred placement, the tricorder, the
field station (`FIELD_STATION.md`), the Borg (`BORG.md`), the Doctor
(`EMH.md`), the channel (`COMMS.md`) and the PADD's screen (`PADD.md` 12),
pointed at one gate.

---

## 1. Why the ship cannot take you (the fiction)

LORE.md 1b says the *Adirondack* **can still transport**, which is how the
ensigns come home. So the gate needs a reason that is true in the story:

> **She locks onto combadges.** Whatever disabled her in February left her
> targeting sensors half blind. A downed ensign is wearing a Starfleet
> transponder, and the shuttle's own transporter, standing beside them,
> boosts it. You are not wearing one. To her sensors you are one more human
> biosign among a county of walking dead, and **she cannot tell you from the
> horde.**

And after the reveal there is a second reason, which is policy rather than
physics: the thing that did this was a Changeling, and **Captain Titus beams
nobody aboard who has not been screened.** The Doctor's biofilter has to be
calibrated against the weapon itself, and the weapon's other half is Borg
nanoprobes (LORE.md 1b), which the Borg among the dead are full of.

## 2. The three keys

| Key | Whose | What the player does |
|---|---|---|
| **Trust** | the ship's | Bring `N` of her crew home (sandbox, default 3). The comms channel's own count of rescues. |
| **Lock** | the ship's | Recover **three pattern enhancers** and hold them, deployed, while the *Adirondack* resolves a lock. |
| **Clean** | each player's | Pass the Doctor's **biofilter screening**: not infected, and a **nanoprobe sample** off one of the Borg among the dead. |

Trust and Lock are shared by the whole crew: a lock, once established, is the
ship's. Clean is per character, asked of the server's copy of that player
(DEV_GUIDE: *Player mod data a client writes is not the server's*), and it
dies with the character: a new character is a new body, and has to be
screened again.

The gate is checked in that order, and the refusal names the first one
missing.

## 3. What the player does

1. **Rescues** (`ENSIGN.md`), exactly as before. Each one counts.
2. **The first rescue brings a debrief.** The ensign says where their away
   kit went down: a `salvage` contact on the map, an approximate fix like a
   probe's, with a pattern enhancer lying in the grass inside it. The
   tricorder plots a salvage site as its own shape (three dots in a
   triangle) and a *Salvage* line. From here the PADD's clearance tab lists
   the lock.
3. **Shepard calls** (thread `LOCK`): why the ship cannot take you, what a
   pattern enhancer is, that the survey team kept spares at the station in
   Muldraugh, and that the probes will pick up anything else that fell.
4. **Three places an enhancer is**, each a different kind of looking:
   * the **debrief** site, above;
   * the **field station** in Muldraugh: one lies on the floor of its
     *Stores* room, placed by the server the first time the station's deck is
     built and loaded, in new saves and old ones;
   * **probes**: while the lock is still owed and the ship has heard about it,
     a probe's find may be a *salvage* site, a crash site with the enhancer
     and some debris, instead of a crystal. The first probe of a save is
     never one. **A lost enhancer is found again by a later probe**, so the
     chain cannot be soft-locked.
5. **The second rescue** (or the lock) brings the Doctor's rule: thread
   `SCREEN`. From here the PADD lists screening.
6. **A nanoprobe sample.** Every Borg the player kills carries one
   (`OnZombieDead`, on the authority, into the corpse's inventory). If the
   sandbox's *Borg among the dead* is *None*, no sample is needed.
7. **Screening**, at any EMH (the shuttle's, or an installed one): *Biofilter
   screening (50 units)* on his panel. Yourself only; refused while infected
   or bitten (he cures you first, that is what he is for); it takes the
   sample.
8. **Deploying the lock.** With three enhancers on you, trust met and no
   lock yet: right-click an enhancer, *Deploy pattern enhancers*. Out in the
   world only, never aboard anything. The server takes the three out of your
   pack and stands them round you in a triangle.
9. **Hold the triangle.** The lock takes **20 game minutes** of somebody of
   the crew standing within 8 squares of its middle. The enhancers hum, and
   the hum is the engine's zombie-attraction noise (`addSound`, like the
   ensign's beacon), louder: the dead come. Nobody near and the clock stops;
   one of the three picked up or knocked away and the lock breaks, the other
   two stay where they are, and it can be deployed again.
10. **The lock resolves.** The enhancers are spent, the ship has the lock for
    good, and everyone within the triangle's range whose own clearance is now
    complete is **beamed straight up**. Anybody not yet screened is told
    why they were left behind. Shepard calls (thread `LOCKED`).
11. From then on the shuttle's *Beam to the U.S.S. Adirondack* works for
    every player whose clearance is complete.

## 4. The sandbox

| Option | Values | Default |
|---|---|---|
| `TrekShuttle.AdirondackAccess` | **Earned** (all three keys) / **Open from the start** / **Rescues only** | Earned |
| `TrekShuttle.AdirondackRescues` | 1 / 2 / 3 / 5 | 3 |

*Open* is the old behaviour, for anybody who wants to skip the story. *Rescues
only* asks for Trust and nothing else.

**Existing saves are grandfathered.** A world whose server has ever built one
of the *Adirondack*'s own decks (not the field station's) was already visiting
her, and the gate is open there for good: the check runs once when the world's
data loads and writes `grandfathered` into the store. An update must never lock
a crew out of their own crops.

## 5. The PADD's clearance tab

A fourth view on the PADD's screen, **Clearance**, a checklist that gives
nothing away:

```
BOARDING CLEARANCE: U.S.S. ADIRONDACK
[x] Crew brought home: 3 of 3
[ ] Pattern enhancers recovered: 1 of 3
[ ] Transporter lock established
[ ] Unknown. Nobody has said what else it takes.
[ ] Cleared to beam aboard
```

A step the story has not revealed is a row that says so and nothing more.
The lock rows appear once the debrief has happened (`told.lock`), and the
screening row once the Doctor's rule has (`told.screen`). A lock being held
shows its minutes. *Open* and grandfathered saves show one ticked row.

"Recovered" counts enhancers the ship has seen picked up from any source,
capped at three: a debrief or probe site's contact becoming `recovered`, and
the station's lying one being taken.

## 6. Where things live

```
shared/TREK/TREK_Config.lua          the numbers below, the two items, the sandbox readers
shared/TREK/TREK_Access.lua          the store (C.AccessKey), the rules both sides
                                     share: mode, the three keys, the refusal, the
                                     PADD's rows, the screening mirror
server/TREK/TREK_AccessServer.lua    the authority: grandfathering, the debrief, the
                                     station's enhancer, recoveries, the Borg's sample,
                                     screening, deploying, holding and resolving the lock
server/TREK/TREK_Missions.lua        calls AccessServer.onRescue after a rescue
server/TREK/TREK_Server.lua          the gate on toAdirondack; the lockBeam move; the
                                     salvage result of a probe; salvage contacts placed
                                     and recovered like crystals
server/TREK/TREK_CommsServer.lua     three events -> lockDue, screenDue, lockedDue
client/TREK/TREK_AccessUI.lua        the enhancer's Deploy menu, the notes, the lift
                                     at the lock, the mirror of the player's screening
client/TREK/TREK_Menu.lua            the beam option greyed with the reason
client/TREK/TREK_AdirondackClient.lua  the refusal note; the lockBeam arrival
client/TREK/TREK_EMHUI.lua           the Screening button
client/TREK/TREK_PaddScreen.lua      the Clearance tab
client/TREK/TREK_MedKit.lua          the salvage site on the tricorder
content/comms/LOCK.json, SCREEN.json, LOCKED.json   Shepard's three calls
tools/gen_access.py                  the enhancer and the sample: meshes, textures, icons
tools/gen_map_symbols.py             TrekContactSalvage
```

## 7. The numbers

| | | |
|---|---|---|
| `C.AccessRescueSteps` | 1, 2, 3, 5 | the sandbox's choices; default the third |
| `C.EnhancersNeeded` | 3 | a triangle |
| `C.DebriefMinDistance` / `Max` | 120 / 320 | from the crew, where the kit went down |
| `C.DebriefSpread` | 40 | the fix's error; the tricorder sweeps 40 |
| `C.ProbeSalvageShare` | 0.4 | of a probe's finds while an enhancer is owed |
| `C.LockRadius` | 2 | squares from the deployer to each enhancer |
| `C.LockHoldRange` | 8 | squares from the middle somebody must stand |
| `C.LockMinutes` | 20 | game minutes of holding |
| `C.LockBeaconMinutes` | 5 | between hums |
| `C.LockBeaconRadius` / `Volume` | 60 / 60 | louder than an ensign's beacon (45): this is the siege |
| `C.LockLiftHours` | 0.5 | how long a lift offered at the lock stays good |
| `C.ScreenCost` | 50 | reserve units for a screening |

## 8. Engine facts, so they are not re-derived

- **`OnZombieDead` fires where the zombie is killed, after its inventory is
  rolled.** `IsoZombie.onKilled` (bci 38-52): off a client it calls
  `DoZombieInventory()`, then fires `OnZombieDead` with the zombie in every
  process that runs it. So the authority adds the sample to
  `zombie:getInventory()` there, and it goes into the corpse with vanilla's
  own loot. A client's handler must not add anything: its copy is not the
  corpse anybody loots.
- **Ask a dead zombie its outfit only once it is dressed**, as `TREK_Borg`
  does (`shouldDressInRandomOutfit()` first; DEV_GUIDE *A getter can dress
  the zombie it is asked about*).
- **The enhancers are world items**, placed with `AddWorldInventoryItem` and
  straightened, removed with `transmitRemoveItemFromSquare`, the ensign's and
  the crystal's route. A lock's squares are checked only on loaded ground; an
  unloaded square is "cannot tell", never "gone".
- **Taking three out of a pack on the server** is
  `inventory:Remove(item)` then `sendRemoveItemFromContainer`, the
  EMH's and the channel's route for a fragment.

## 9. What will bite you

- **Every older test beams to the Adirondack.** The simulation's sandbox has
  `AdirondackAccess = 2` (Open) beside `StartState = 2`, for the same reason:
  those scenarios were written for a ship that could. `access()` sets it back
  to Earned itself.
- **A gate checked on the client only** is not a gate. The server refuses
  `toAdirondack` with the same `Access.refusal` the menu greys with.
- **The PADD tab must not leak.** Its words for an unrevealed step are fixed
  and say nothing; `test_helm.py` draws the tab before and after each reveal.
- **The lock's hold is measured on the server**, from its own copy of where
  the crew are, and ticks outside any loaded-ground branch; only the
  "is each enhancer still there" check needs the ground.

## 10. Checks

| Check | Catches |
|---|---|
| `test_multiplayer.py` `access` | grandfathering; Open and Rescues-only; the gate and its order; the debrief contact once; the station's enhancer placed once and counted when taken; the probe's salvage result, never first; a salvage site recovered and counted; the Borg's sample on the authority only and not without Borg; screening refused infected, without a sample, for someone else, and done once; deploying refused inside, short, untrusted; the hold pausing with nobody near, breaking when one is taken, resolving, spending the enhancers, and lifting the screened; the move refused and then granted |
| `access_multiplayer` | the server's copy decides screening; the mirror reaches only its owner; one lock for two players; the lift reaches only the screened; no client world edits |
| `test_helm.py` | the Clearance tab in bounds, before and after each reveal; the EMH panel's new row |
| `test_assets.py` | the two items, their models and icons, the sandbox options, the translations, the salvage symbol |
| `test_comms.py` | the three threads and their flags |
