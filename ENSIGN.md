# The downed ensign

The working guide for `ROADMAP2.md` 1.7, the mod's first mission, in the shape
`PROBES.md`, `EMH.md` and `UNIFORMS.md` use: what the player does, what
happens, how the figure is made, the numbers, the engine facts not to
re-derive, and what will bite you.

It is built on four systems that already existed: the contact store and its
map view (`PROBES.md`, `MAP_MARKERS.md`), deferred placement (a contact is a
record until a player loads its ground), the tricorder's sensor sweep
(`MEDICAL_SET.md`) and the uniforms (`UNIFORMS.md`). Almost nothing here is a
new mechanism; it is those four pointed at a person.

Every ensign is rolled male or female, so this guide says "the ensign" and
"they" rather than guessing.

---

## 1. What the player does

1. **A distress call comes in.** A warbling chime, and a note over the
   character's head: *"Distress call: Ensign Maren Novak is down, 320 tiles
   NE. Answer it at the sensor console."* It reaches every crew member,
   aboard or not.
2. **Answer it at the sensor console** -- aboard, *Shuttlecraft ->
   Long-range sensors*. The call sits under the probe controls with who it
   is, which division, how far and which way, and **Accept** / **Decline**.
   Declining costs nothing. Ignoring it costs nothing either: an unanswered
   call fades after half a game day and another comes later.
3. **Accepting starts the clock** and puts a life-sign contact on the map --
   an approximate fix, drawn with the personnel symbol, the ground uncovered
   around it, listed on the console with distance and bearing. The console
   then shows *Rescue under way* and the hours left.
4. **Get there** -- on foot, by car, or by calling the shuttle down nearby.
5. **Find them with the tricorder.** The map's fix can be up to forty tiles
   out. A sensor sweep within forty tiles of the ensign plots a **blue
   cross** -- a third shape on the plot, apart from the lifesign squares and
   the crystal rings -- and adds a *Starfleet life sign* line with the
   distance and bearing.
6. **The ensign is sitting on the ground, doubled over, in uniform.** Their
   combadge chirps every few seconds while you are within thirty tiles, and
   the same signal is why the dead in the neighbourhood are walking toward
   them.
7. **Right-click them.** *Examine Ensign ...* says who they are, how they are
   and how long they have. *Beam Ensign ... to safety* works within three
   tiles, and is shown greyed, with the reason, from further away.
8. **The ship thanks you.** The ensign is gone, everyone is told, the
   rescuer is handed two ration packs and a hypospray, and the replicator
   learns three patterns from the ensign's tricorder: antibiotics, a suture
   needle and a splint first, and further down the list on each rescue after.

If the clock runs out first, the beacon stops, the mark leaves the map, the
figure is taken away, and the crew are told. No second chance on that
ensign -- and no soft-lock: another call comes, because this is a repeatable
mission and not a quest line.

---

## 2. What happens

### The call

`M.serviceDistress()` in `server/TREK/TREK_Missions.lua`, on the authority's
game-minute tick, outside every cabin-loaded branch, like probes and cures.

- **The ship has to be able to hear.** `M.hearing()` is true once the cabin
  has been built (a crew has been aboard) and there is dilithium in the core
  or the reserve. **This is the one line cold start (1.6) changes:**
  *commissioned* will replace *has dilithium*, and nothing else here moves.
- **The first call is scheduled, not made**, `C.DistressFirstHours` after the
  ship first hears -- one game hour, a few real minutes, so a fresh world
  meets its first ensign in the first sitting and not the instant the crew
  first beam aboard.
- **One at a time, and never while a rescue is live.** A pending call or a
  live mission, and the timer waits.
- **The target is chosen when the call is made**, so the call can say how far
  and which way. It is picked the way a probe's endpoint is: a random bearing
  from where the **crew** are (`Ship.worldOrigin`), a distance between
  `C.EnsignMinDistance` and `C.EnsignMaxDistance`, and `U.inWorld` on the
  result, `C.EnsignBearingTries` times. A call with nowhere valid to point
  waits `C.DistressRetryHours` and tries again.
- **Everything about the ensign is rolled once and stored**: name, division,
  body, square. Every crew member sees the same ensign, and a restart does
  not re-roll them.
- **An unanswered call lapses** after `C.DistressOfferHours`, and the next is
  scheduled.

### Answering

`distressAnswer { id, accept }`, validated: crew access; the player aboard by
the **server's** copy of where they are; and the id is the call actually
pending -- so two crew answering at once make one mission, and an answer to a
call that faded while the panel was open is refused by name instead of
bringing it back.

Accepting creates a `downedPersonnel` contact with the mission on it:

| field | |
|---|---|
| `x, y` | the approximate fix the map draws, up to `C.EnsignReportSpread` off |
| `tx, ty, tz` | where the ensign actually is |
| `name, division, body, item` | who they are, and which of the six figures |
| `deadline` | acceptance + `C.EnsignLifeHours`, in world hours |
| `placed, ex, ey, ez` | set when the figure is on the ground |

A `downedPersonnel` contact **with no deadline is not a mission** and is left
alone: the store's own tests make synthetic ones, and a clockless contact
would otherwise be timed out on the first pass.

### The figure

`M.serviceMissions()`, same tick. A live mission whose figure is not placed
asks `U.chunkLoaded` for the four corners of its search area and does nothing
until a player has legitimately loaded that ground -- the crystal rule, for
the same reason: an unloaded square is "cannot tell", never "nothing there".
Then it searches rings outward from `tx, ty` for a square with a floor,
nothing solid, **no water**, and **no safehouse**, and puts one world item
there -- `TrekShuttle.TrekEnsign<M|F><Division>` -- straightened to face
south, the side the camera sees.

- **Loaded and genuinely nowhere to sit them** (a lake, the middle of a
  warehouse) retires the mission as `invalid`, says so in the log, tells the
  crew the signal broke up, and schedules another call soon.
- **A figure that is no longer on its square** -- carried off, say -- is
  noticed on loaded ground only, and put back where it was on the next pass.

**The ensign is identified by the contact, never by their own mod data.** The
client finds them by `ex, ey, ez` in the store it already has, and the server
checks the square for the item. Nothing depends on an item's mod data
surviving a world-item packet, which is a claim this project has never tested.

### The beacon and the chirp

While the figure is placed and its ground is loaded, every
`C.BeaconEveryMinutes` game minutes the server calls vanilla's
`addSound(object, x, y, z, radius, volume)` at the ensign's square. That is
the engine's own zombie-attraction noise -- a car alarm, a gunshot -- so what
it draws is **the dead that are already in that block**, as many as the
server's population settings put there. Nothing is spawned.

Each client near the ensign also plays the combadge chirp at their square,
every `C.ChirpEveryMs`, within `C.ChirpRange`. That is presentation, like the
lights and the shields: each machine does its own, and none of it is ship
state.

### The rescue

`rescueEnsign { id }`, validated: crew access; the contact is live, a
`downedPersonnel`, and placed; the player is on the ensign's level and within
`C.EnsignRescueRange` of their square by the **server's** copy of where they
are; and the figure is actually on that square. Then, in one handler:

1. the figure is removed with `transmitRemoveItemFromSquare`;
2. the contact becomes `completed`, and the map stops drawing it;
3. the reward is granted -- **exactly once**, because the `completed` check is
   the first thing the handler does;
4. every client is told, and the next call is scheduled.

### Running out of time

When `deadline` passes, the mission is `expired` whether or not anybody is
near: the clock runs outside every loaded-ground branch (DEV_GUIDE: *A guard
gated on loaded ground never sees the case it exists for*). A figure on
loaded ground is removed there and then; otherwise the square goes on
`ensignRemovals` and the figure is taken away the next time somebody loads it
-- `s.ghosts`, again.

---

## 3. The figure, and why it is not an animation

The question was whether the game would let the ensign *move*. It will not,
and the reasons are worth keeping:

- **Animation needs a character.** A `.x` animation drives a skeleton, and
  only an `IsoGameCharacter` has one. A world model, a weapon, the hull --
  all static meshes with no bones.
- **`IsoSurvivor` is not networked.** Lua can reach it (it is on the
  exposure list), but its only vanilla call sites are paper-doll avatars
  built with a nil cell, and of the 22 classes in the jar that reference it,
  none is under `zombie/network/`. A server-made survivor would be invisible
  to every client.
- **`IsoZombie`** posed with `setFakeDead` / `setCrawler` is animated and
  networked -- and every Lua route to spawn one is `DebugUIs/` or the
  `/createhorde2` admin command. That is the *jar is not the API* shape.
- **`IsoDeadBody`** is networked and one call away
  (`RandomizedWorldBase.createRandomDeadBody`, exposed, and ending in
  `GameServer.sendCorpse`), but it is a corpse: it rots, it is a lootable
  container, it can be dragged and burnt, and it needs a named outfit this
  mod has not built. It is the right tool for a *failed* rescue and the wrong
  one for a living ensign.

**So the ensign is a static model -- but not a modelled one.** The game ships
the animations *and* the skinned bodies they drive, as text `.x`.
`tools/xskin.py` reads a vanilla body, the boilersuit rig the duty uniform
already rides, and a hairstyle; poses all three at one frame of the game's
own `Bob_SitGround_Pain_Stomach` -- sitting on the ground, doubled over, a
hand pressed to the stomach -- and bakes them into one mesh.
`tools/gen_ensign.py` builds a 512x512 texture from four 256x256 sources --
the vanilla skin, **the mod's own generated duty uniform**, a tinted hair
texture and a flat boot colour -- and paints a stain on the front of the
uniform where the hand is.

Six items, two meshes, six atlases: both bodies, all three divisions. The
render they were judged on is `design/art/ensign/ensign_sheet.png`.

```sh
python tools/gen_uniform.py TrekShuttle/42    # first: the figures wear these textures
python tools/gen_ensign.py  TrekShuttle/42
```

The lying-down poses the game has (`Bob_Deadbody_OnBack`,
`Bob_Idle_FloorOnFront`, `Bob_SitGround_SleepIdle`) were all rendered and all
read as a body. Sitting and holding themselves reads as *hurt and alive*,
which is the whole brief.

**The "alive" signal has to come from everything except the mesh**: the pose,
the chirp, the tricorder's cross, the countdown on the console, the examine
text. That was the design constraint, and it is closer to Star Trek than a
writhing body would have been.

---

## 4. The numbers, and why

| | | |
|---|---|---|
| `C.DistressFirstHours` | 1 | game hours from the ship first hearing to the first call |
| `C.DistressIntervalHours` | 36 | from one call ending (rescued, lost, declined, lapsed) to the next |
| `C.DistressOfferHours` | 12 | how long an unanswered call waits |
| `C.DistressRetryHours` | 1 | when a call found nowhere to point, or a rescue had nowhere to sit |
| `C.EnsignLifeHours` | 72 | the clock, from acceptance. Generous: a reason to go, not a trap |
| `C.EnsignMinDistance` / `Max` | 150 / 450 | squares from the crew -- a real walk, a short drive |
| `C.EnsignReportSpread` | 40 | the map fix's error; the tricorder sweeps 40, so a sweep from the fix finds them |
| `C.EnsignPlaceRadius` | 8 | rings searched for somewhere to sit them |
| `C.EnsignRescueRange` | 3 | tiles from the ensign to beam them up |
| `C.EnsignMenuMargin` | 1 | right-click slack around their square |
| `C.BeaconEveryMinutes` | 10 | game minutes between pulses |
| `C.BeaconRadius` / `Volume` | 45 / 45 | a gunshot is about 50; this is the block, not the town |
| `C.ChirpEveryMs` / `C.ChirpRange` | 6000 / 30 | the chirp, per client |
| `C.RescuePatternsPerRescue` | 3 | patterns per rescue, from `C.RescuePatterns`, in order |

**Why no dilithium cost for the beam.** The crystal economy already carries
the Doctor's cure and the replicator. A rescue that spent power would be a
rescue players declined, which defeats a feature whose whole point is going.

**Why patterns and not a crystal.** ROADMAP2: "avoid immediately awarding
another full crystal after the opening crystal". Patterns are for ever, and a
fixed order means each rescue teaches something new until the list runs out.

---

## 5. Where things live

```
shared/TREK/TREK_Config.lua        every number above, the six item ids, the names,
                                   the reward, C.DivisionLabels
shared/TREK/TREK_Probes.lua        the store: contacts, the pending call
                                   (P.distress), the live mission (P.mission),
                                   removals, P.newId
shared/TREK/TREK_Util.lua          U.compass (shared now: the server names a
                                   bearing in the call), U.worldHours
server/TREK/TREK_Missions.lua      the authority: hearing, calls, answers, the
                                   figure, the beacon, the clock, the rescue
server/TREK/TREK_Server.lua        the move handler records a player's return
                                   point on the server's copy (section 6)
client/TREK/TREK_EnsignUI.lua      the right-click menu, the chirp, the notes
client/TREK/TREK_ProbeUI.lua       the call, Accept / Decline, the countdown
client/TREK/TREK_MedKit.lua        the cross on the tricorder plot
client/TREK/TREK_Core.lua          the six refusals' words
media/scripts/trekshuttle.txt      the six items and models, the two sounds
tools/xskin.py                     the skinned .x reader and pose baker
tools/gen_ensign.py                the six figures and their renders
tools/gen_medical.py               the combadge chirp and the distress chime
```

---

## 6. Engine facts, so they are not re-derived

- **A text `.x` animation's rotation keys are written conjugated** relative to
  the Direct3D reading of the same quaternion. Measured, not assumed:
  `MaleBody.x` carries a short animation whose first key is its own frame
  pose, and the conjugated reading reproduces the frame matrices to 3e-6
  where the plain one is off by 2.0. `gen_ensign.py` re-measures on every run
  and refuses to bake if neither reading agrees.
- **A body's frame matrices are not its bind pose.** They are the first frame
  of that file's embedded walk; the bind pose lives only in the SkinWeights
  offsets. So skinning is `sum(w * p * offset * posed_world)`, and the frames
  are used for nothing but bone lengths.
- **Bob's animations drive Kate** with only the rotations borrowed: every
  bone keeps its own translation except the root, whose translation is where
  the pelvis sits -- which is the pose, not the proportions.
- **The male crew cut is a cap**, not a haircut: it covers the front of the
  scalp and leaves the back bare, which a hunched pose shows first. The
  figures use `Bob_Hair_Short`.
- **`addSound(IsoObject, x, y, z, radius, volume)`** is an ordinary
  `GlobalObject` static with 47 vanilla Lua call sites, including
  `server/Camping/SCampfireSystem.lua` and `server/Traps/STrapGlobalObject.lua`.
- **`IsoGridSquare:playSound(name)`** plays at a square, from ordinary shared
  code (`ISActivateCarBatteryChargerAction.lua:29`).
- **`SafeHouse.isSafeHouse(sq, "", false)` answers for every safehouse.** The
  empty name is neither a member nor the owner (bci 92-111). The last
  argument is `false` because `true` lets *disable safehouse while the owner
  is away* (bci 52-82) report a real safehouse as none.
- **Player mod data a client writes is not the server's.** The return point
  is set on the client's copy of the player; a dedicated server never saw it,
  so `Ship.worldOrigin` asked about a player standing in the cabin had no
  answer there. The `move` handler now records it on the server's copy before
  a beam up or a walk in. This was also a live bug in probes -- a probe
  launched aboard on a server would have been refused for want of a fix --
  that single player could never show, because there the two copies are one.
- **World static models and characters share a unit**, as far as the files
  say: a dropped katana is drawn by the same model block it is held with, at
  no scale. So the figure is baked at the character's own size. Worth a look
  in game (section 8).
- **The baked mesh winds its faces the way the hull does** -- same majority
  orientation against the centroid as the hull (confirmed in game) and a
  vanilla bucket. The previewer draws both sides, so it cannot show an
  inside-out mesh on its own.

---

## 7. What will bite you

**The atlas, not the pose.** Four textures go into one, and a UV outside
0..1 on any source rig wraps into the neighbouring quadrant -- skin on a
sleeve, hair on a boot. `quad_uv` wraps each part inside its own quadrant.
And a texel sampled from a source texture's transparent gutter would draw
black in game with no warning; the suit rig was checked and none of its faces
lands in one.

**The wound is placed by rig position, not by texel.** The uniform's atlas is
auto-packed, so "the stomach" is not a rectangle in the sheet (UNIFORMS.md:
*a texture painted in texture space will be wrong*). `gen_ensign.py` refuses
to write a figure whose wound covered fewer than forty texels, because a
stain in the wrong place is still a perfectly plausible texture.

**The dark band across the shoulders is the uniform, not a fault.** It is the
duty uniform's collar band, which runs round the back of the neck. Standing
up it hides under the chin; doubled over it is the first thing the camera
sees.

**Constructed translation keys.** The division is shown through
`C.DivisionLabels`, spelled out, and the six item ids through
`C.EnsignItemIds`, spelled out -- the first draft pasted both together, and
`tests/test_assets.py` read the pasted prefix as an item that did not exist.
Spelled out, it checks every one.

**A test that passes because the ground is unloaded.** The chirp's range
check first survived a mutation that deleted it: the test stood two hundred
squares away, where the ensign's square is simply not loaded and nothing
chirps anyway. It stands fifty away now and asserts the ground is loaded.
Same shape as `flight_alone()`'s rule: *a scenario that never reaches the
condition is not a test of it*.

**Answering from outside the ship.** The server refuses it, correctly -- and
the first draft of the tests walked the player out and then answered, and
read the refusal as a bug. The test helper answers from the pad.

---

## 8. Checks

| Check | Catches |
|---|---|
| `tests/test_multiplayer.py` `distress` | not listening before boarding or without dilithium; the first call scheduled rather than instant; one call at a time; the target measured from the crew and inside the world; wrong-id and out-of-ship answers refused by name; decline and lapse each scheduling the next; racing answers making one mission; the clock and the approximate fix |
| `ensign_world` | no figure until the ground loads; one figure, the right one, straightened; the beacon's timer, square and radius; the chirp from the ensign's square and not from fifty squares; the tricorder's distance and bearing, and nothing out of range; the menu's margin and the greyed beam; too far refused; a double rescue paying once; the reward list moving on |
| `ensign_edges` | a carried-off figure put back; the clock expiring with the ground unloaded and the figure removed when it loads; no ground; water; a safehouse; a never-placed mission leaving nothing to clear |
| `ensign_multiplayer` | the server's position fix for a player aboard (and a probe launched aboard); both clients hearing the call; racing answers; one figure on both machines; the rescuer's own menu; the rescue measured on the server; the figure, the notes, the patterns and the supply reaching exactly who they should; no client world edits |
| `tests/test_helm.py` | the console's call block and countdown drawing in bounds, Accept / Decline greyed for their own reasons and on the stick; the tricorder's cross on the range limit, its line, and no line when nobody is in range |
| `tests/test_assets.py` | the six items, six models, two meshes, six textures, two sounds, the translation keys, and the replicator blocklist |

**Seventeen mutations, one at a time, all caught** -- after the one above was
fixed: the double-pay guard, the answer's id and aboard checks, a clock gated
on loaded ground, the removal list, the straightening, safehouse and water,
the beacon's timer, the rescue's reach, the server's return point, the click
margin, the chirp's range, the tricorder's range, deafness without
dilithium, an instant first call, and Accept always live.

---

## 9. Not proven in game, and what to look at

**Seen working in single player, 2026-09-24**, the whole loop in a fresh
world: the call arrived about an hour of game time after boarding, was
accepted at the sensor console, the figure was placed when the crew stepped
out 40 tiles from it -- beside the map's mark, which is exactly how far off
the long-range fix is allowed to be -- the tricorder found it, and the
rescue learned Antibiotics, Suture Needle and Splint. The figure draws and
the right-click lands on it.

The one moment of doubt was the design working: the player walked to the
mark and saw nobody, because the mark is a circle forty tiles across and the
ensign was on its far edge. The tricorder is what closes that gap, so the
call's note and this guide both say so.

Still open from the list below: player size and facing on close inspection,
whether the beacon drew anything, the chirp over a long rescue, vanilla's
own options on the figure, and two clients.

The route, in a fresh world or an existing one (the call needs only a built
cabin and dilithium in the core):

1. Beam aboard, and play on for **about an hour of game time**. The call
   arrives as a note with a chime.
2. *Shuttlecraft -> Long-range sensors*. The call is under the probe
   controls. **Accept.**
3. Open the map: a personnel mark with the ground uncovered around it.
4. Go there. Within forty tiles, use the tricorder -- the blue cross.
5. Find the ensign sitting on the ground. Listen for the chirp.
6. Right-click them: **Examine**, then **Beam to safety** from within three
   tiles.

What to look at while doing it:

1. **Does the figure read as a person who is hurt?** And **are they
   player-sized** -- stand next to them.
2. **Which way do they face**, and is the combadge on their left breast? The
   rig says it is; a static model loader that mirrored X would say otherwise.
3. **Does the right-click land on them?** Aim at the body, not the ground
   beside it. `C.EnsignMenuMargin` is the dial.
4. **Does the beacon draw zombies?** The call sites are ordinary server code;
   nobody here has watched it work.
5. **Is the chirp audible, positional, and bearable** after a minute of it?
6. **Two clients**: both hear the call, one accepts, both see the mark and
   the figure, one beams them up, both see them go, and only one reward.
7. **Vanilla's own options on the figure.** It is a world item, so the game
   will offer its usual world-item actions beside *Examine* and *Beam to
   safety* -- *Grab*, probably. It weighs 90, which should put it out of
   reach; if somebody can pick the ensign up, the server puts a figure back
   on the square on its next pass, and the weight or a flag wants looking at.

## 10. Deliberately not built yet

- **A corpse when the ensign is lost.** `createRandomDeadBody` would put a
  body in a Starfleet uniform where they sat, which is the one job that tool
  is right for. It needs a named outfit in `media/clothing/clothing.xml`, and
  it has no vanilla Lua call site, so it is a thing to prove on its own.
- **The ensign aboard.** ROADMAP2 is right: a second persistent person is a
  whole new object with its own state. They are beamed "to safety", off
  screen.
- **Probes finding personnel.** The kind is on the store and the sweep draws
  it; nothing but a distress call creates one yet.
- **The skant as a reward.** `UNIFORMS.md` section 7 has it scoped: its tunic
  needs the body-texture pipeline rather than the garment one, and a mission
  reward is a good reason to build that pipeline.
- **Rank on the figure.** Every one of them is an ensign.
