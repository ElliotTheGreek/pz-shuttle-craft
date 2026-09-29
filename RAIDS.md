# Raids: when the pattern buffer overflows

The design for the mod's first fight the player is **invited to**: Captain
Titus calls with a request, the player has five game hours to get ready, and
**Accept** beams them into the fight -- aboard the *Adirondack*, at the field
station, or at a Starfleet outpost in the county -- and home again when it is
over. In the shape `ACCESS.md` and `ENSIGN.md` use: the fiction, what the
player does, what happens, the numbers, where things live, the engine facts
it rests on, and what will bite.

**Status: the outpost raid is built (1.13.0, 2026-09-28) and not yet seen in
game; the field station and the Adirondack are designed and not built.**
Section 11 is the order, and its first step is a check that could change the
Adirondack's half. Section 12 is what was built and how to test it.

---

## 1. Why the dead come aboard (the fiction)

The Doctor's biofilter (`ACCESS.md` 1) does not destroy what it strips out of
a pattern. It **holds it** -- in the transporter's pattern buffer, the only
place a transporter can put anything. Every ensign beamed up, every screening,
every lift from a lock leaves nanoprobe-laden residue there.

Borg nanoprobes rebuild dead matter (LORE.md 1b: "a corpse reassembled to a
template and animated"). A pattern buffer full of nanoprobes and human
residue is exactly the material they need. When it reaches capacity the ship
has to **purge** it, and a purge is a controlled rematerialisation through an
emitter into a contained space. Controlled until it is not: what comes out is
not residue. It walks.

So a raid is a purge that is going to go wrong, and the Captain knows it:

- **Aboard the Adirondack**, the purge vents through the nearest emitter to
  whichever deck the buffer's routing picks -- the bridge included.
- **At the field station**, the station's own transporter buffer has been
  filling since June (`FIELD_STATION.md`), with nobody to purge it.
- **At an outpost** -- a Starfleet supply cache in the county, the kind the
  survey team set up and lost -- the ship offloads the buffer remotely,
  through the outpost's pad, to keep it off her decks. The outpost is where
  it comes out.

It is Trek-shaped (a transporter accident; this shelf is named after one) and
it is **caused by play**: the more the crew rescue and screen, the faster the
buffer fills, so raids are a consequence of the campaign rather than a dice
roll. The Borg look of what comes out is literal -- the residue rebuilds to
the nanoprobes' template.

**What the story never says**: that anybody is doing this on purpose. The
Changeling reading (a rescued "ensign" who opened the buffer) is available as
a one-time twist later and is deliberately not part of this design.

## 2. What the player does

1. **The call.** Once the player's own clearance is complete (`ACCESS.md`:
   `Access.refusal(player) == nil`), a request can come in. A chirp, a note
   over the head, and an **LCARS request panel** opens: Titus's portrait, her
   request in two or three lines, where it is, how many she expects, the
   countdown, and **Accept** / **Decline**. The panel can be closed and
   reopened -- from the PADD (a *Requests* row on the Clearance tab) and from
   the aboard menu -- for as long as the request stands.
2. **Five game hours** to get ready: eat, load a phaser, fetch a friend, pick
   a weapon off the armoury rack. The panel's countdown is on screen, and a
   note warns at one hour and at ten minutes.
3. **Accept** beams the player straight to the raid, wherever they are
   standing (the ship's transporter, not the shuttle's -- no pad needed). The
   server records **where they were**: that is where they come back to.
4. **The fight.** The dead stream out of the emitter in **waves** -- a few at
   first, then more -- for as long as the buffer has patterns left. The panel
   becomes a small HUD strip: *Buffer 64% -- 23 remaining*.
5. **Done** when every pattern has come out and every one of them is down.
   The server says so, the survivors have **sixty seconds** to loot (a
   *Beam back now* button skips it), and then everyone who came is beamed
   back to where they accepted from.
6. **Or not done**: every raider dead, or everyone who came left by other
   means, or the raid's hard limit reached. The ship contains the rest itself
   -- at the cost section 6 lists.

**Declining** or **letting it lapse** is always allowed and never punished
beyond section 6's consequences. Nobody is ever teleported without pressing
Accept.

In multiplayer, the request goes to **every cleared player**; each one who
accepts is beamed in; the raid starts with the first and the others can join
while it is running (the panel says *Join*). Each is returned to their own
point.

## 3. The three kinds of raid

| | Where | Emitter (the spawn) | Scaled for |
|---|---|---|---|
| **Adirondack** | one of her decks, picked at random -- the bridge included | the deck's turbolift car (the buffer vents through the lift's emitter) | close quarters, her crew beside you |
| **Field station** | its one long floor | its lift car | close quarters, the station's crew |
| **Outpost** | a site the server picks on wild ground in the county | the outpost's transporter pad | open ground, the most dead |

### 3.1 The outpost

A camp the ship **builds for the raid** on open, natural ground (the rule
`TREK_Wild` uses: grass, dirt, sand; no road, no water, no safehouse) in a
clear 11 x 11 area, 300 to 1,200 squares from the crew:

- a **transporter pad** in the middle -- the Adirondack's own pad tiles
  (`trek_adirondack_02_148/149`); the dead come out of it;
- a **warp core**, a **replicator** and an **EMH station** -- the installation
  kits' tiles (`INSTALLATIONS.md`), placed as **scenery**: tagged, not in the
  installations registry, so none of them works and none can be taken away;
- **two tents** and **four supply crates** -- vanilla camping tents and
  crates, the crates stocked from a raid loot list (medical, ammunition for
  the Starfleet weapons, rations, a chance of dilithium).

Placed by the server **after** the first raider has arrived and the ground
has loaded round them -- the deferred-placement rule (DEV_GUIDE: *Never
build where no player is standing*), exactly how a landing site is found:
move first, hold the player on the spot, build, release.

After the raid the pad and the three machines are **taken away** (a free warp
core in a field is the installations' economy undone); the tents and the
crates stay, looted or not, as a ruin on the map.

### 3.2 Aboard the Adirondack and the field station

The deck is picked when the call is made, so the request can name it ("Deck
1. The bridge."). Her crew on that deck stay at their posts -- they are part
of the scene -- and the raiders are **tagged** so the crew director does not
sweep them away (section 8).

## 4. The waves

A raid holds a **buffer** of `N` patterns, fixed when the call is made:

    N = C.RaidBase[kind] + C.RaidPerPlayer * (players who accept)

-- recomputed as players join, never lowered. They are released in waves from
the emitter every `C.RaidWaveSeconds` real seconds, `C.RaidWaveSize` at a
time, while fewer than `C.RaidAliveCap` of the raid's own are standing (so a
slow fight does not bury itself). Each is an ordinary hostile zombie spawned
with `addZombiesInOutfit` -- the call the crew system already proves -- in a
Borg outfit most of the time (`C.RaidBorgShare`) and a generic one otherwise,
and tagged in its mod data with the raid's id.

The raid is **won** when the buffer is empty and none of its tagged dead are
standing. It is **lost** when no raider is alive and present for
`C.RaidAbandonMinutes`, or at `C.RaidHardLimitMinutes`.

## 5. Home again

Each raider's return point is recorded by the **server** when they accept, on
the server's copy (DEV_GUIDE: *Player mod data a client writes is not the
server's*), exactly as the field station's way down does. The way back is a
granted move (`raidReturn`), so it goes through the same protocol as every
beam and the speed anti-cheat's rationing. A raider who was aboard the
shuttle or the Adirondack when they accepted goes back there -- their return
point is the pad they left from.

A raider who dies stays dead. A raider who quits mid-raid and comes back later
finds the raid over and is sent home on their first tick (the raid record
remembers who was in it).

## 6. What declining costs

A choice with no weight is not a choice, and a choice with too much is a
trap. Each kind has one consequence, mild, visible and temporary:

| Kind | Declined, lapsed or lost |
|---|---|
| Adirondack | the deck is **sealed** for a game day: the lift will not stop there, and its crew are off their posts (the crew director's post list) |
| Field station | the station goes **dark** for a game day: its store drained, lights red, the replicator and Doctor down |
| Outpost | the supply cache is lost -- nothing else |

And each raid **won** pays: the crates (outposts; a one-in-four chance of a
dilithium crystal in one of them), replicator patterns from the rescue list,
and it **counts like a rescue** toward rank (`TRAITS.md` 3.3) for every raider
present at the end. (The design first had a share of the ship's reserve
refilled; left out, so a raid never reaches into the power ledger.)

## 7. The numbers (first guesses, to be played)

| | | |
|---|---|---|
| `C.RaidFirstDays` | 2 | game days after a player's clearance to the first request |
| `C.RaidEveryDays` | 3 to 5 | between requests, rolled |
| `C.RaidOfferHours` | 5 | how long a request stands |
| `C.RaidWarnAt` | 1 h, 10 min | the countdown notes |
| `C.RaidBase` | adk 16, fst 16, outpost 30 | patterns in the buffer |
| `C.RaidPerPlayer` | 10 | more per raider |
| `C.RaidWaveSize` / `C.RaidWaveSeconds` | 4 / 20 | |
| `C.RaidAliveCap` | 14 | the raid's own standing at once |
| `C.RaidBorgShare` | 0.6 | |
| `C.RaidLootSeconds` | 60 | after the last one falls |
| `C.RaidAbandonMinutes` / `C.RaidHardLimitMinutes` | 5 / 60 | game minutes |
| `C.OutpostMinDistance` / `Max` | 300 / 1200 | squares from the crew |
| `C.OutpostSearch` | 20 | squares round the site searched for the camp: with the camp's own 5, the whole search stays inside the ground loaded round an arriving raider |

Sandbox: **Raids** (Off / Rare / Normal / Frequent -- the interval), and
**Raid size** (Small / Normal / Large -- a scale on `N`). Off by default is
*not* the answer: the feature is the point, and *Off* is there for servers
that do not want it.

Which kind is offered is weighted by what the crew have: no field station
opened, no field-station raids; the outpost is always possible.

## 8. Engine facts, and the checks they need

- **The crew director deletes strangers.** `TREK_CrewServer`'s sweep removes
  every zombie aboard the Adirondack or the field station that is not a live
  crew member (`sweepStrays`), within seconds. Raid zombies carry a raid tag
  in mod data and the sweep must skip a tag belonging to a **live** raid --
  and take them once the raid is over, which is its job anyway.
- **The pathfinder does not know runtime walls** (`CREW.md`: the crew walk
  routes of the mod's own). A zombie chasing a player across her decks may
  stall on walls, or worse. **This is the first thing to check** (section 11,
  step 1). Outposts stand on the real map, where pathing is vanilla's own, and
  are unaffected -- which is why they are built first.
- **Spawning on a deck.** `addZombiesInOutfit` at A.Z on a built deck is what
  the crew already do; a raid zombie is the same body without the pacifying
  (`setUseless`, `setNoTeeth`, `setAvoidDamage` left off).
- **The teleport** is the client's move, granted by the server (`Core
  .requestMove`), like every other long move; arrival holds the player on the
  spot until the ground is there (the Adirondack's `beginArrival`, the
  station's surfacing). An outpost's arrival waits for the camp too.
- **The panel** is an `ISPanelJoypad` in the helm's LCARS (DEV_GUIDE: *Every
  panel must work with a controller*), with Titus's portrait from
  `gen_captain_art.py`. Not an `ISModalDialog`: it has to be reopenable and
  show a countdown.
- **Everything is the server's**: the request, who accepted, the buffer, the
  waves, the tags, the outcome, the return points. A client asks and draws.

## 9. Where things will live

```
shared/TREK/TREK_Raids.lua          the record (C.RaidKey): the request, the raid, who is in it;
                                    the rules both sides read (may I accept, the HUD's numbers)
server/TREK/TREK_RaidsServer.lua    scheduling, the call, accept/decline, the outpost's camp,
                                    waves, the outcome, consequences and rewards, return
client/TREK/TREK_RaidsUI.lua        the request panel, the HUD strip, the notes, the moves
server/TREK/TREK_CrewServer.lua     the sweep skips a live raid's dead
content/raids/*.json                Titus's requests and outcomes, by kind (generated, as the
                                    channel's are)
```

## 10. Checks (when built)

| Check | Catches |
|---|---|
| `raids` | no request before clearance; one request at a time; the lapse; decline and its consequence; accept records the return point on the server and moves the player; a raid in each of the three kinds; the waves' size, pace and cap; the win and the return; the loss; the rewards once; the outpost's camp placed only after arrival, on wild ground, its machines scenery and taken away after |
| `raids_multiplayer` | the request on both clients; each accepts and is returned to their own point; a second joining mid-raid; the tags keep the crew sweep off the raid's dead; no client world edits |
| `test_helm.py` | the request panel and the HUD strip, in bounds and on the stick |

## 11. Order of work

1. **The pathing check on her decks.** Spawn a hostile zombie on a built
   Adirondack deck in a real game and let it chase: across a room, through a
   door, round a corner. What it does decides whether Adirondack and station
   raids stay in one room (the lift lobby and whatever opens off it) or use
   the whole deck. Half a session, and the most likely thing to change this
   design.
2. **Outposts, end to end**: the request, the panel, accept, the camp, waves,
   the win, home. Real map, real pathing -- the whole loop proven where the
   engine is on our side.
3. **The field station**, then **the Adirondack**, as step 1 allows.
4. **Consequences and rewards**, then the sandbox, then two players.

## 12. What was built: the outpost (1.13.0)

- `shared/TREK/TREK_Raids.lua`, `server/TREK/TREK_RaidsServer.lua`,
  `client/TREK/TREK_RaidsUI.lua`; the moves `raidIn` and `raidOut` in
  `TREK_Server`'s MOVES, granted only to a raider; the sandbox's **Raids** and
  **Raid size**.
- **The request** comes only while somebody is cleared to beam aboard her
  (`Access.refusal` nil). The panel opens by itself; *Captain Titus's request*
  on any right-click reopens it while it stands. Accept greys with the reason
  the server would give. Decline by everybody who could come ends it early.
- **Accepting** writes the way home on the server's copy of the player (the
  cabin, a deck of hers or the station's, or a square of the map), then the
  client beams out to the site and is held there while the ground loads. The
  server searches for the camp once a raider is present and every corner of
  the search is loaded, builds it, and sends each raider their stand spot.
  The first wave is one interval after the camp stands.
- **The camp's ground** (`campGround`): the county's natural floor, nothing
  solid, no tree, nothing anybody built, no building. A summed-area table
  picks the centre with the most good ground, its pad's two squares good and
  nine in ten of the rest; ties go to the nearest.
- **The dead** are spawned with `addZombiesInOutfit` at the pad, tagged in
  mod data **on the server** (a client's copy never carries the tag), counted
  from the server's zombie list each wave. Borg outfits 60%, vanilla's generic
  otherwise.
- **The strip** at the top of the screen is 380 by 26 and nothing else.
- **Retreat**: *Beam out of the raid* on any right-click, any time; after a
  win it reads *Beam back now*.
- Not built yet: the crew director's exemption (only needed aboard), the
  consequences for the other two kinds, and the Changeling twist.

**Checks:** `raids` and `raids_multiplayer` in `test_multiplayer.py`,
`raid_panel` in `test_helm.py`. Twenty-six mutations, one pass at a time,
all caught -- three of them only after the tests learned rough ground where
the nearest camp's pad is blocked, a home square somebody has built on, and
an Accept while raids are off.

### How to test it in game

Sandbox: **Adirondack access = Open from the start** (the raid needs a player
she can beam), **Raids = Frequent** (the first request an hour of game time
after a player is cleared, then every half day to a day).

1. Play for an hour of game time. The Captain's request opens with a chirp:
   her portrait, the outpost's distance and bearing, how many to expect, the
   countdown. Close it; right-click anywhere, *Captain Titus's request*, and
   it is back.
2. Get ready -- a weapon, food, a friend -- and press **Accept**.
3. You are beamed to the site and held while it loads; then you are put down
   beside the pad, in a camp of a warp core, a replicator, a Doctor's station,
   two tents and four crates. The strip at the top reads *Pattern buffer 100%*.
4. Twenty seconds later the first four come out of the pad, then four more
   every twenty seconds, never more than fourteen standing.
5. When the buffer is empty and the last one is down: *The buffer is clear*,
   sixty seconds to loot the crates, then home to exactly where you accepted.
   The pad and the machines go; the tents and crates stay.

What to look at: whether the camp stands on sensible ground and looks like a
camp; whether the dead come out of the pad and come for you; the pace and the
count; the loot; the trip home, from the cabin, from her decks and from the
street; *Beam out of the raid* mid-fight.

