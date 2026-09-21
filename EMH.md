# The Emergency Medical Hologram — working guide

**Built 2026-09-20, and not yet seen in a game.** This was the plan; it is now
the record. Every decision in it was made before the work started and almost
all of them survived contact — what changed, and why, is in *Where the plan
met the engine* at the end, which is the section worth reading if you are
about to change any of this.

The play-through in §14 is the thing still owed. It needs **no fresh world**:
the station and the square were authored into the interior by the refit, so
`C.BuildRev` 22 is the whole migration and a cabin built at revision 17 or
later gets him on the next arrival. That makes the Doctor the first system in
this mod to reach an existing save.

The spec, from `ROADMAP.md`:

> **EMH** — a wall switch that brings up a static model of the Doctor, a
> dialogue panel, full diagnosis and treatment, infinite supplies, and **the
> only cure for zombie infection** (decided). Treatment runs on the server.

All six parts of that are built. What `ROADMAP.md` does not fix, and this file
does:

| | |
|---|---|
| **The model** | generated with the fal.ai image-to-3D toolkit, imported by `tools/import_gltf.py`, vendored under `tools/assets/trek_emh/` |
| **Supplies** | infinite — nothing to restock, no doses, no dressings. Diagnosis and treatment are unlimited; they draw on the ship's reserve, which is what the author's own code already says |
| **The cure** | **one whole dilithium crystal**, and **twelve in-game hours aboard**. The only price in the feature |
| **The patient** | anyone aboard, and treating somebody else asks them first |

`DEV_GUIDE.md`'s *Rules that exist because they were broken* applies to every
line of this. `MULTIPLAYER.md` is the client/server split. `MEDICAL_SET.md` is
the four instruments whose primitives this inherits. `REPLICATOR.md` is the
worked example of a cabin fixture with a panel behind it.

---

## 1. The shape of it

### 1.1 Files

| File | New? | What it holds |
|---|---|---|
| `shared/TREK/TREK_EMH.lua` | **new** | where he stands, who is in reach, who may be a patient, the sandbox mode, the cost. No side effects; loads everywhere, so the panel greys itself for exactly the reason the server refuses |
| `shared/TREK/TREK_Medical.lua` | edit | `Med.CURE`, `Med.removeForeign`, `Med.cure`, `Med.publish` |
| `shared/TREK/TREK_Config.lua` | edit | the constants in §9, and one line in `C.ReplicatorBlocked` |
| `client/TREK/TREK_EMHUI.lua` | **new** | the menu, the dialogue panel, the light, the consent prompt, the replies |
| `server/TREK/TREK_Server.lua` | edit | six handlers, the cure register, the per-minute tick |
| `server/TREK/TREK_Build.lua` | edit | `B.serviceEMH`, `B.emhAt`, a build phase |
| `client/TREK/TREK_Core.lua` | edit | the new `DENIALS` entries |
| `media/scripts/trekshuttle.txt` | edit | `item TrekEMH`, `model TrekEMHModel`, `sound TREK_EmhAppear` |
| `media/models_X/TREK_EMH.x` | **new** | generated |
| `media/textures/TREK_EMH.png` | **new** | generated |
| `media/sandbox-options.txt` | edit | `TrekShuttle.EMH` |
| `lua/shared/Translate/EN/` | edit | `IG_UI.json`, `ItemName.json`, `Tooltip.json`, `Sandbox.json` |
| `tools/gen_emh.py` | **new** | mesh, texture, portrait and the renders it is judged on |
| `tools/import_gltf.py` | edit | two parameters — §2.3 |
| `tools/assets/trek_emh/` | **new** | the vendored GLB and its licence note |
| `design/art/emh/` | **new** | the concept image, the raws, the contact sheet, the renders |
| `tests/` | edit | §13 |

**Nothing is added to the `.tbx`.** The station at 3,3 and the clear square at
2,4 were authored into the interior by the refit; that is why this feature is
cheap in the cabin and expensive only in art.

### 1.2 State

One field in the ship state, and one register on the server.

```lua
s.emh      = true | nil      -- the Doctor is up. Ship state: every client
                             -- sees the same hologram standing on the deck
s.emhCures = { [username] = <world age hours when it completes> }
```

**There is no cooldown.** Treatment does nothing to a healthy patient and the
cure takes twelve hours, so a held button is already its own limit; a cycle
guard here would be the cooldown-wearing-a-hat that `REPLICATOR.md` threw out
by name.

`s.emhCures` is a table in a state that is transmitted whole on every change,
which `DEV_GUIDE.md` warns about — it is allowed here because it is **bounded
by the number of people simultaneously under treatment**, each entry is one
number, and entries are removed when they complete. It is not a log and must
never become one.

**`s.emh` is cleared in `OnInitGlobalModData`**, beside the block that clears
`s.flying` (`TREK_Server.lua:1643`). A hologram does not survive a world
reload, and clearing it deletes the entire class of stale-flag bug.
`s.emhCures` is **kept**: a cure in progress is paid for and must survive.

### 1.3 Protocol

```
client -> server            server does
  emhSummon                 stands the model up at 2,4, s.emh = true
  emhDismiss                takes it down, s.emh = nil
  emhLook   { who }         reads that patient's body and reports it back
  emhTreat  { who }         treats, or offers if `who` is somebody else
  emhCure   { who }         cures, or offers
  emhAccept { token }       the patient agreeing to be treated
  emhDecline{ token }

server -> client
  emhFindings{ who, hurt, infected }        to the ASKER: what he can see
  emhOffered { token, from, what, cost }    to the PATIENT: a yes/no
  emhTreated { counts }                     to the patient, and a note
  emhCureStarted { hours }                  to the patient
  emhCured   { }                            to the patient: clear your own
                                            body-level infection state
  denied     { why, ... }                   to whoever asked
```

**`emhLook` is not a convenience.** In multiplayer a remote player's body
damage does not exist on a client to be read — see §10 — so the panel cannot
work out what is wrong with the crewman on the biobed by itself. The server
looks and answers, and the panel draws what it is told. For yourself the panel
reads your own body directly and sends nothing.

Every command is validated server-side: alive, `Ship.canUse`, the sandbox is
not *Off*, `EMH.inReachOf(player)` measured on the server's own copy of where
they stand, and — for anything naming a patient — that the patient is really
aboard, measured the same way. **A client is a request, never a fact**,
including about who the patient is.

---

## 2. The model of the Doctor

He is a static world model standing on 2,4, placed and removed by the server
exactly as the warp core and the replicator are placed.

### 2.1 How the mesh is made

The pipeline exists and has been used once already, for the hull:
`tools/assets/type6_shuttle/type6_shuttle.glb` → `tools/import_gltf.py` →
`TREK_Shuttle.x` (430 KB, imported whole, no decimation). A figure goes the
same way.

1. **The concept image** — the Gemini Image toolkit (`generate-image`), a
   front-on full-length figure, neutral stance, arms at the sides, flat
   background, no face detail that a 32-pixel-wide silhouette cannot carry.
   He is a **hologram of a Starfleet medical officer**: uniform, combadge,
   nothing that copies a likeness (§8).
2. **The mesh** — the fal.ai toolkit's image-to-3D wrapper (installed, active,
   credentials configured). It returns a GLB on fal's CDN.
3. **Vendor it.** Download it to `tools/assets/trek_emh/trek_emh.glb` with a
   `SOURCE.txt` beside it naming the model slug, the date and the prompt. This
   is the convention `tools/assets/type6_shuttle/` and
   `tools/assets/quaternius_dispatcher/` already set, and the reason for it is
   in `import_quaternius.py`'s header: **regenerating the mod must not require
   network access, Blender, or a third-party package.** The GLB is the raw;
   re-running fal gives a *different* figure, not the same one again.
4. **`python tools/gen_emh.py TrekShuttle/42`** — imports the GLB, recolours
   the texture, writes `TREK_EMH.x`, `TREK_EMH.png`, the panel portrait, and
   two renders into `design/art/emh/`.
5. **Look at the renders.** `tools/preview_model.py`, at yaw 0 and yaw 40.
   *Render it and look* is in `DEV_GUIDE.md` twice and it has caught four
   faults in the hull and three in the replicator.
6. **`python tools/meshbbox.py`** on the result, against the warp core's 1.30.

### 2.2 What makes him a hologram rather than a mannequin

**The texture, and it is entirely under our control.** `gen_emh.py` takes the
GLB's own diffuse PNG and rewrites it deterministically before it is shipped:

- **collapse to one hue.** Luminance-mapped to the LCARS blue ramp
  (`H.P.blue`, `0.60 0.80 1.00`) — a hologram is monochrome light, and a
  monochrome figure cannot read as a shop dummy the way a flesh-toned one can;
- **horizontal scanlines**, one pixel in four at about 0.75 brightness, which
  is what says "projected" in a still image, and the game's camera only ever
  gives it a still image;
- **lift the floor**, so the darkest parts glow rather than going black
  against a dark deck.

Deterministic — no randomness — so re-running the generator writes a
byte-identical file and a regenerated asset is never a silent diff. That rule
is in `gen_warpcore.py`'s header and it applies here.

### 2.3 Two changes `import_gltf.py` needs

`import_glb(source, mesh_output, texture_output, texture_file,
target_length=5.0, target_width=3.0)` was written for a hull and does two
things wrong for a figure:

- **it hardcodes the mesh name** `"TREKShuttle"` in `mesh.emit(...)`. Add a
  `name="TREKShuttle"` parameter;
- **it fits to a footprint**, scaling by
  `min(target_width/xspan, target_length/zspan)`. A standing figure must be
  fitted by **height**. Add `target_height=None`, and when it is given, scale
  by `target_height/yspan` instead.

Both are additive and the hull's call site keeps its behaviour unchanged —
`tests/test_assets.py` already checks `TREK_Shuttle.x`, so a regression shows
up immediately.

**Size: `C.EmhHeight = 1.25` tiles.** The warp core is 1.30 and stands in a
passage the crew walk down; a person is a shade shorter than the ship's power
plant. `meshbbox.py` prints the result and the number to trust is the
**bounding box**, not the constant — `DEV_GUIDE.md`'s bat'leth lesson, where
`SPAN = 0.46` drew 0.531.

### 2.4 The item and model blocks

In `media/scripts/trekshuttle.txt`, `module TrekShuttle`, beside
`TrekWarpCore`:

```
    item TrekEMH
    {
        ItemType = base:normal,
        Type = Normal,
        DisplayName = Emergency Medical Hologram,
        DisplayCategory = Furniture,
        Icon = TREK_Shuttle,
        Weight = 90.0,
        WorldStaticModel = TrekEMHModel,
        StaticModel = TrekEMHModel,
        Tooltip = Tooltip_TREK_EMH,
    }

    model TrekEMHModel
    {
        mesh = TREK_EMH,
        texture = TREK_EMH,
        scale = 1.0,
    }
```

`module TrekShuttle`, not `module Base`: that rule is about `WeaponSprite`
only, and `StaticModel` resolves inside the mod's own module — which is how
the hull, the replicator and the warp core all work.

**And `"TrekShuttle.TrekEMH" = true` goes into `C.ReplicatorBlocked`**, beside
the hull and the torpedo. A player must not be able to replicate a second
Doctor and stand him in the galley.

### 2.5 Standing him up and taking him down

In `TREK_Build.lua`, the warp core's code with the names changed:

```lua
function B.emhAt(sq)            -- count, never assume; a second one is the
                                -- "Two shuttles" signature indoors
function B.serviceEMH()         -- idempotent in BOTH directions:
    -- s.emh and none standing  -> AddWorldInventoryItem + straighten
    -- not s.emh and any        -> removeWorldItem(sq, C.EmhItem) for ALL
```

Five things it must do, each of which has already cost this project a bug:

1. **Count before placing.** A world item is saved and `U.clearSquare`
   deliberately preserves world items, so a pass that does not look first
   stands a second Doctor there at every rebuild.
2. **Remove all of them, not the first.**
3. **Straighten.** `IsoWorldInventoryObject`'s constructor writes
   `Rand.Next(0, 360)` into an unset yaw. Straighten on placement *and* on
   every later pass, because that later pass is the only thing that will ever
   reach a crooked Doctor in an existing save.
4. **Run as a build phase**, in the `phases` list beside `furnishReplicator`
   and `furnishCore` — **not only on the per-minute timer**. `B.forceRebuild`
   wipes everything but the floor, so `TREK_Rebuild()` deletes the Doctor and
   `s.emh` still says he is up; the build phase is what puts him back.
5. **Use `removeWorldItem(sq, fullType)`**, the named removal that already
   exists (`TREK_Build.lua:204`), and go through `removeSynced` →
   `transmitRemoveItemFromSquare`. `removeWorldObject` throws on a server.

An unloaded chunk needs no ghost list. `s.emh` is the truth and the pass is
idempotent in both directions, so a removal missed because nobody was aboard
self-heals the next time somebody is. Write that down in the file; it is
stronger than the hull's `s.ghosts` and it is worth knowing why.

---

## 3. The station, and the squares

`industry_01_15`, tag `emhPanel`, at 3,3 — from the hull's own wall set,
carrying neither `solid` nor `solidtrans`, so 3,3 is still deck. The Doctor
stands at 2,4. Both are already in `TREK_InteriorLayout.lua`.

A right-click resolves to the **floor square under the cursor**, and the
Doctor is a tall model, so the menu answers on a named set rather than on one
square:

```lua
C.EmhMenuSpots = { {2,3}, {3,2}, {3,3}, {2,4}, {3,4} }
```

— the station, the square you stand on to work it, the locker above it, the
Doctor's own square and the head of the biobed.

**The warp core's margin must be tightened in the same pass**, from a
one-square box to an explicit set, because its box currently reaches 2,4 and
would answer on the Doctor:

```lua
C.CoreMenuSpots = { {1,3}, {0,3}, {1,2}, {1,4}, {2,3} }
```

`TREK_WarpCore.lua`'s `W.isCore` changes from a `MARGIN` comparison to a
lookup in that list. Six lines, and it makes the rule below enforceable.

**The rule, for all three fixtures, in `tests/test_layout.py`:** *no fixture's
menu squares may contain another fixture's own square, or the transporter
pad.* The own squares are the core's 1,3, the replicator's 0,5, and the EMH's
2,4 and 3,3. Check it against the existing two before writing it — with the
core tightened, all three pass.

---

## 4. The dialogue panel

`TREKEMHWindow`, an `ISPanelJoypad` built from the helm's LCARS parts
(`H.pill`, `TREKLcarsButton`, `H.P`), so the ship's third console does not look
like a third mod.

**It is a dialogue, not a control panel**, and that is a requirement rather
than a flourish. The Doctor speaks: a line at the top of the panel that
changes with what he has been asked and what he found, above his portrait.
Every action is a thing he says he is doing and then a thing he reports having
done.

| Part | What it shows |
|---|---|
| Portrait | `media/ui/TREK_EmhPortrait.png`, generated, keyed, vetted at panel size |
| His line | one or two sentences, from `IGUI_TREK_Emh*`, chosen by state |
| Patient | a row of the people aboard; you are first and selected by default |
| Findings | what is wrong with the selected patient, itemised, from the same lists the treatment uses — so the readout cannot drift from what the button does. **Your own body is read here; anybody else's arrives from the server on `emhFindings`**, because a remote body does not exist on this client to be read (§10) |
| Infection | **whether they are carrying the zombie infection** — the one thing the medical tricorder deliberately will not say. Same rule: yours locally, theirs from the server |
| Crystals | `TREK.Power.crystals()`, because that is what the cure costs |
| **Treat** | `C.EmhTreatCost` from the reserve. Greyed, with a reason, when there is nothing to treat |
| **Full readout** | `M.openHealthPanel` from `TREK_MedKit.lua` — vanilla's `ISHealthPanel` at `C.MedDoctorLevel`. Never `ISHealthPanel.cheat` |
| **Cure the infection** | one crystal. Greyed, with a reason, when they are not infected or when the core is empty |
| **Dismiss** | takes the hologram down |

The panel is the way in and the way out: opening it sends `emhSummon` if he is
not already up, and the *Dismiss* button sends `emhDismiss`. Closing the window
does not dismiss him — a crewman closing his own panel must not take the Doctor
away from somebody else.

Shown-and-greyed, never hidden; the panel closes itself when the player walks
out of reach (`ISFeedingTroughUI:prerender` is vanilla's precedent). Controller:
`insertNewLineOfButtons`, `setISButtonForB`, a visible focus state, focus
handed back on close.

**There is no `emhDiagnose` command.** Opening a health panel on a body is
client UI and the sandbox mode is readable in every process; a handler whose
only job is to answer "yes" is a round trip that can drift out of step with
the panel that calls it.

---

## 5. The patient, and consent

**Any player aboard may be the patient.** The panel lists everyone in the
cabin; the server resolves the patient from its own copy of where people are
standing and refuses anyone who is not aboard.

Treating yourself needs no consent. **Treating somebody else asks them
first:**

```
asker    picks a crewman, presses Treat or Cure
         -> emhTreat { who = "<username>" }

server   validates the asker, the sandbox, the reach, and that `who` is
         really aboard. Spends NOTHING yet. Mints a token.
         -> emhOffered { token, from, what, cost }   to the PATIENT

patient  ISModalDialog, yes/no, naming who is asking and what it costs
         -> emhAccept { token }   or emhDecline { token }

server   re-validates everything from scratch, checks the token has not
         expired (C.EmhOfferMs), then treats or cures
```

`ISModalDialog:new(x, y, width, height, text, yesno, target, onclick, player,
param1, param2)` — public, with ordinary-player call sites in
`ISTradingUI.lua`, `ISInventoryPane.lua` and `ISPostDeathUI.lua`.

The offer expires, is single-use, and is re-validated on acceptance, because
between the offer and the answer the asker can walk away, the core can be
emptied, and the patient can leave the ship. **Nobody can force-heal — or
force-anything — another player**: that is the padlock-and-safehouse rule from
`MULTIPLAYER.md` applied to bodies.

In single player there is nobody else aboard, so the offer path never runs.
Test it anyway, with two clients, or it is untested by construction.

---

## 6. Treatment and the cure

**Both run on the server**, which is the spec — and the spec is not merely
allowed, it is the only place either of them *can* run.

`BodyDamage.Update()` decides who simulates a body, at bci 21–62:

```
21  getstatic GameClient.client ; 24 ifeq -> 63    not a client: run the whole sim
51  IsoPlayer.isLocalPlayer()   ; 55 ifne -> 62    a client, own body: return
58  BodyDamage.RestoreToFullHealth()               a client, REMOTE body: wiped
```

So in multiplayer **body damage is simulated on the server and nowhere else**,
and a remote player's body on a client is restored to full every single tick —
it is not stale, it is not there at all. The server is not a second-best place
to treat somebody from; it is the only machine that knows they are hurt.

`BodyDamageSync` is the push to a watching doctor's client, not what maintains
the server's copy: the server maintains it by running `Update()` itself. And
`syncBodyPart` is the matching push for a single part, which is why it too is
`if (!GameServer.server) return`.

Two things follow that are easy to get wrong:

- **the panel cannot read another patient by itself** — hence `emhLook` in
  §1.3;
- **`MEDICAL_SET.md` says a body "belongs to the client that owns them and
  syncs from there".** That is right for your *own* body and it is the reason
  the hypospray works client-side. It is not a general rule, and this file is
  the first place in the mod that needed the difference. The hypospray's
  behaviour in a real multiplayer game deserves its own look; it is out of
  scope here and it goes on the pinned two-player session.

### 6.1 Treatment — unlimited supplies, and it leaves a bite alone

**Supplies are infinite; power is not.** A treatment spends `C.EmhTreatCost`
from the ship's reserve, and the Doctor will not come up at all when the
reserve is empty. That is not a limit invented here — it is what five places
in the author's own code already say, and this file is where they come true:

> *"spent by the replicator and later by the EMH"* — `TREK_Power.lua:175`
> *"the EMH will draw on the same reserve"* — `trekshuttle.txt:96`
> *"a crew with no crystals has a galley fixture and a hologram that will not
> switch on"* — `trekshuttle.txt:97`
> and `TREK_Config.lua:760`, `TREK_Replicator.lua:353`, `TREK_Util.lua:158`

At 25 units against a crystal's 5,000 that is two hundred treatments to a
crystal — unlimited in play, and honest about what he runs on. There is
nothing to restock, no doses, no dressings: the *supplies* are infinite, which
is what `ROADMAP.md` asks for. The reserve is the lights.

```lua
Med.treatWith(patient, Med.TREATMENTS)        -- the hypospray's list
Med.treatWith(patient, Med.SKIN)              -- the regenerator's, unskipped
Med.removeForeign(patient)                    -- glass and bullets
Med.publish(patient)                          -- syncBodyPart per part
```

`Med.SKIN` is applied **without** `Med.obstructed`: the regenerator refuses to
close skin over glass, and the Doctor takes the glass out first, which is the
whole reason he is better than the instrument in your pocket.

`Med.removeForeign` is two setters per part and the second takes two
arguments:

```lua
part:setHaveGlass(false)
part:setHaveBullet(false, 0)        -- (boolean, int). One argument throws.
```

**Treatment must leave a bite and the zombie infection exactly where it found
them.** The hypospray's six-dose limit, the regenerator's scope and the reason
the EMH exists all rest on the bite being the one thing you come home for.
Treatment never touches `Med.CURE`.

### 6.2 The cure

Per body part, **`part:RestoreToFullHealth()`** — a deliberate inversion of
`DEV_GUIDE.md`'s rule about convenience methods. That rule forbids it to the
hypospray *because* it clears the bite. The EMH is the one thing in the mod
that may clear a bite, and the disassembly says the short call is also the
**safe** one here: it writes its thirty-seven fields by direct putfield and
never calls `SetBitten`, so it side-steps the trap in §7.1.

Then once, on the character, on the server:

```lua
damage:setInfected(false)
damage:setIsFakeInfected(false)
damage:setReduceFakeInfection(false)
damage:setInfectionTime(-1.0)                 -- -1, NOT 0
damage:setInfectionMortalityDuration(-1.0)
```

**Both levels, in one pass.** `BodyDamage.isInfected` is a one-way latch
re-derived from the parts every tick and *skipped* once true: clearing it alone
is undone next tick, and clearing the parts alone never clears it.

Then `Med.publish(patient)` — `syncBodyPart(part, 0xFFFFFFFFFFF)` for every
part — and `Net.toClient(patient, "emhCured", {})`.

**That last message is not optional.** `syncBodyPart`'s 42-bit mask carries
`BodyPart` fields only, so the `BodyDamage` flags above and the infection
moodle do not ride it. On receipt the patient's own client clears them on its
own character:

```lua
damage:setInfected(false) ... setInfectionMortalityDuration(-1.0)
character:getStats():set(CharacterStat.ZOMBIE_INFECTION, 0)   -- U.try'd
```

The moodle matters more than it looks: the block that writes
`ZOMBIE_INFECTION` runs **inside** the countdown, and the countdown is gated on
`isInfected()`. Clear the infection and that block stops running, so the last
value it wrote is the value that stays — a perfect cure with the moodle still
on screen saying you are dying.

Every entry is read back ask → fix → ask, as `Med.treatWith` already does. The
asks are `part:IsInfected()`, `part:bitten()` and `damage:isInfected()`.

### 6.3 The twelve hours

The cure is not instant. On acceptance the server:

1. checks `TREK.Power.crystals() > 0`;
2. `TREK.Power.takeCrystal()` and `Ship.commit()` — **the crystal is spent
   now**, and the panel says so before the button is pressed;
3. `s.emhCures[username] = getGameTime():getWorldAgeHours() + C.EmhCureHours`;
4. `Net.toClient(patient, "emhCureStarted", { hours = C.EmhCureHours })`.

On `EveryOneMinute` the server walks `s.emhCures`:

- **the patient left the ship** (`U.isInteriorPlayer` false) → drop the entry,
  tell them, and the crystal is gone. Not a refund. The treatment is a
  commitment, not a reservation, and that is the whole weight of the number;
- **it is due** → §6.2, then drop the entry;
- **they are not online** → leave it. It survives a relog because the ship
  state is saved.

Both halves of the biobed carry `BedType = goodBed`, so a patient sleeps it
off; on a server they do not, and twelve game hours at the default day length
is about half an hour confined to the cabin. That is the cost, and it is
deliberate.

---

## 7. The traps

### 7.1 `SetBitten(false)` infects the limb

The obvious cure clears the bite with `part:SetBitten(false)`. In its
**one-argument** form the `if (bitten)` guard ends at bci 102 and everything
after it runs regardless of the argument, writing `isInfected = true` and
calling `generateBleeding()`. A player who paid a crystal and slept twelve
hours would wake up infected, on a limb that was now bleeding, with the mod
reporting a successful cure.

**Vanilla's own admin health cheat has this bug in two places**
(`ClientCommands.lua:490`, `ISHealthPanel.lua:222`), which is why the call
looks right. That is `DEV_GUIDE.md`'s *the jar is not the API* one level in:
**a vanilla call site proves a method is reachable, never that it is
correct.**

Use `SetBitten(false, false)` — in the two-argument form bci 33 is
`iload_1; ifeq -> 105` and the whole block sits behind the guard — or
`RestoreToFullHealth()`, which never calls either. §6.2 uses the latter.

### 7.2 The other four

- **`setInfectionTime(0)` leaves a running clock.** `Update()` bci 371–377
  only initialises the countdown when the value is negative. Write `-1.0`.
- **`setHaveBullet(false)` throws.** It is `(boolean, int)`.
- **`B.forceRebuild` deletes the Doctor** and `s.emh` still says he is up. The
  build phase in §2.5 is what repairs it, and the test must assert the repair
  *after* asserting the placement, never the other way round.
- **`syncBodyPart` is a no-op on a client.** Its first instruction is
  `getstatic GameServer.server; ifeq -> return`. Calling it from `client/`
  looks like a sync and is nothing; `static()` should forbid it there.

---

## 8. The Doctor's voice and likeness

He is the **Emergency Medical Hologram**, a descriptive designation, and not a
named character. His lines are written for this mod — dry, impatient,
competent — and not quoted from the show; the famous one is not his signature
line here. There is no speech audio and no imitated voice: the summon sound is
a synthesised chime through the procedural pipeline `tools/gen_medical.py`
already uses. Nothing in `design/art/emh/` is derived from a frame of
anything, and the concept prompt in §2.1 describes a uniform and a stance, not
a person.

`ROADMAP.md` already sets the standard — *"is it Star Trek without copying a
frame of the show"* — and this is the feature where it bites.

---

## 9. Constants

```lua
---------------------------------------------------------------------------
-- The Emergency Medical Hologram
---------------------------------------------------------------------------
C.EmhItem          = "TrekShuttle.TrekEMH"
C.EmhStation       = { x = 3, y = 3 }          -- the wall panel, authored
C.EmhSpot          = { x = 2, y = 4 }          -- where he stands
C.EmhHeight        = 1.25                      -- tiles; the core is 1.30
C.EmhMenuSpots     = { {2,3}, {3,2}, {3,3}, {2,4}, {3,4} }
C.EmhRange         = 2                         -- the replicator's and the core's
C.EmhOfferMs       = 30000                     -- a consent offer expires
C.EmhTreatCost     = 25                        -- reserve units; 200 to a crystal
C.EmhCureCrystals  = 1                         -- whole crystals, not units
C.EmhCureHours     = 12                        -- in-game hours aboard
C.EmhLight         = { r = 0.55, g = 0.80, b = 1.00, radius = 4 }
C.EmhFull, C.EmhOff = 1, 2
```

And in `C.ReplicatorBlocked`: `["TrekShuttle.TrekEMH"] = true`.

**Sandbox**, `TrekShuttle.EMH`, two values, default 1:

| | |
|---|---|
| 1 **Full** | the Doctor as designed |
| 2 **Off** | the station is inactive and says so |

An absent option reads as 1 — the feature as designed — which is the rule
`C.ReplicatorPatterns` and `C.TorpedoFire` both follow.

**There is deliberately no value that keeps the Doctor and removes the cure.**
`ROADMAP.md` marks *the only cure for zombie infection* **(decided)**, and a
server setting that switches off a decided headline feature is not a setting,
it is a second opinion. A server owner who does not want the cure turns the
EMH off.

---

## 10. Engine facts, established

Checked with `tools/pzapi.py` (exists, public), `tools/javadis.py` (**under
what condition**) and a grep of vanilla Lua for a call site whose path is not
`AdminPanel/` or `DebugUIs/`. **Do not re-derive these.**

| Fact | Where |
|---|---|
| **`BodyPart.SetBitten(boolean)` — one argument — infects the part.** The guard ends at bci 102; `isInfected = true` and `generateBleeding()` follow unconditionally | `javadis.py` |
| **`SetBitten(false, false)` is correct** — bci 33 `iload_1; ifeq -> 105` puts the whole block behind the guard | `javadis.py` |
| Vanilla's admin health cheat uses the broken form, twice | `ClientCommands.lua:490`, `ISHealthPanel.lua:222` |
| **`BodyDamage.isInfected` is a one-way latch**, re-derived from the parts each tick (bci 280–300) and **skipped once true** (bci 271). Both levels must be cleared in one pass | `javadis.py` |
| **`RestoreToFullHealth()` writes 37 fields by putfield and never calls `SetBitten`** — right for the cure, wrong everywhere else in this mod | `javadis.py` |
| **`getInfectionTime() < 0` is the "not started" sentinel** — `Update()` bci 371–377. Write `-1.0` | `javadis.py` |
| **The infection moodle freezes rather than clearing**: bci 1877 gates the countdown on `isInfected()`, and bci 2007–2014 is its only writer | `javadis.py` |
| `setHaveGlass(boolean)`; **`setHaveBullet(boolean, int)`** | `ISRemoveGlass.lua:73`, `ISRemoveBullet.lua:69` |
| `Capability.CanMedicalCheat` gates only added pain, instant completion and the consent bypass — **not** the foreign-body setters | `ISRemoveGlass.lua:66,83` |
| **`syncBodyPart(part, mask)` is a `GlobalObject` static that returns unless `GameServer.server`**, then sends `BodyPartSync` to `getConnectionFromPlayer(part:getParentChar())` — **that one player's own connection** | `javadis.py` |
| Its mask is **42 bits**; `BodyPartSyncPacket.parse` loops `i = 0..41` and calls `BodyPart.sync(reader, i+1)`. `0xFFFFFFFFFFF` is "everything", which is what vanilla passes | `javadis.py` |
| **It carries `BodyPart` fields only** — `BodyDamage` flags and the `Stats` moodle do not ride it | `javadis.py` |
| `getGameTime():getWorldAgeHours()` is public on `zombie.GameTime` with non-debug client call sites | `ISButtonPrompt.lua:520`, `WinterIsComing.lua:8` |
| `ISModalDialog:new(x, y, w, h, text, yesno, target, onclick, player, p1, p2)` | `ISTradingUI.lua`, `ISInventoryPane.lua`, `ISPostDeathUI.lua` |
| `cell:addLamppost(x, y, z, r, g, b, radius)` returns the light; `removeLamppost(light)` takes it back | this mod, `TREK_Torpedo.lua:180-194` |
| `panel.doctorLevel` on the instance opens every Doctor gate; `ISHealthPanel.cheat` is `false or getDebug()` | `MEDICAL_SET.md` |
| **No vanilla humanoid model is static** — every one is `static = false` with an `animationsMesh`, so none can be borrowed as a `WorldStaticModel`. The mod makes its own | `scripts/generated/models_characters.txt` |
| `import_glb` handles glTF Y-up, smooths normals, and takes one embedded PNG diffuse texture | `tools/import_gltf.py:138,171` |

---

## 11. Who owns what

| | |
|---|---|
| The hologram standing on the deck | **Server**, `s.emh`, placed and removed as a world item |
| Who may use him | **Server** — alive, `Ship.canUse`, the sandbox, and the reach, measured on its own copy |
| Who the patient is | **Server**, from its own copy of who is aboard. Never sent by a client |
| Consent | **The patient's client** raises it; the server mints, expires and re-validates the token |
| **The body** | **Server**, written directly, pushed with `syncBodyPart` |
| The body-level infection flags and the moodle | **The patient's client**, on `emhCured`, because the packet does not carry them |
| The crystal, the cure register | **Server**, ship state, one writer |
| The light at 2,4, the panel, the portrait | **Each client, for itself.** Scenery and presentation |

---

## 12. Build order

Fix, then design, then migrate.

**Phase 0 — make the simulation honest.** Everything in §13.3. Most of the
mutation list cannot fail without it, and two of the additions close holes
that exist today: `pz_sim` keeps world items out of `getObjects()`, so
`U.clearSquare`'s world-item guard and `forceRebuild`'s treatment of the
replicator and the warp core are **untested right now**.

**Phase 1 — the model.** §2, end to end, including the two `import_gltf.py`
parameters. Renders judged before any Lua is written: the Doctor is the one
part of this feature that cannot be fixed later without redoing it.

**Phase 2 — the shared floor.** `TREK_EMH.lua`, `Med.CURE`,
`Med.removeForeign`, `Med.cure`, `Med.publish`, the constants, the blocklist
entry, the tightened core margin, the translation keys. `test_layout.py` and
the vacuity floors land here.

**Phase 3 — the server.** Six handlers, the cure register, the per-minute
tick, `B.serviceEMH` and its build phase, the `DENIALS` entries, the `static()`
additions.

**Phase 4 — the client.** The menu, the dialogue panel, the light, the consent
prompt, the replies. `emh()` and `emh_multiplayer()` come green here, and every
mutation in §13.2 is run **one pass at a time** — two overlapping runs share
the files and leave each other's edits behind, which has happened here before.

**Phase 5 — migration.** `C.BuildRev` 21 → 22, so a cabin built before the
refit gets its station. Nothing else moves and no fresh world is needed, which
makes the EMH the first system in this mod that reaches an existing save.

**Phase 6 — the documents.** `README.md` (features, sandbox, known limits),
`ROADMAP.md` (the EMH out of *Then: ship systems*), `MULTIPLAYER.md` (the
authority table), `MEDICAL_SET.md` (its open question about the tricorder is
answered: the tricorder stays silent and the EMH is the thing that knows), and
`DEV_GUIDE.md`, which gains two sections: *a vanilla call site proves
reachability, never correctness*, and *a derived flag that latches needs
clearing at both ends*.

---

## 13. Testing

### 13.1 `emh()` and `emh_multiplayer()`

**Play it through the menu and the panel, never by calling the handlers.**
Driving a handler directly passes against a build whose button is wired to
nothing, which is how the torpedoes once shipped unfireable and the replicator
once shipped un-right-clickable. Use `stand_at`, `SIM.aim`, a
`SIM.contextMenu()`, `TREK.EMHUI.fillMenu`, `menu:labels()`, and the `click()`
helper that **fails when the option is not there**.

`emh()`: the option appears at 2,3 and is greyed from across the cabin; the
panel opens and the Doctor speaks; summoning stands **one** model at 2,4,
straight, **counted before anything rebuilds**; dismissing removes it, also
before any build pass; `TREK_Rebuild()` deletes him and the next build phase
puts him back; **treat** clears both lists plus glass and a bullet and
**leaves a bite and the infection exactly as it found them**; **cure** clears
the bite, every per-part infection field, every body-level field and the
moodle, asserted field by field; the cure takes **one crystal** and the reserve
does not move; with no crystals it is refused and the refusal names dilithium;
the cure does not land until `C.EmhCureHours` have passed; leaving the cabin
drops it and the crystal does not come back; sandbox *Off* greys the option
with a reason and refuses server-side; an empty reserve refuses the summon
and says why.

`emh_multiplayer()`: a stranger is refused under `TrekShuttle.Access = 2`;
**the offer is raised on the patient's screen and nowhere else**; declining
spends nothing; accepting spends one crystal and the count falls on both
panels; an expired token is refused; a client naming somebody else as the
patient in a forged command changes nothing; the second client sees the
hologram standing and sees it go; no client writes the ship state or edits the
world.

### 13.2 Mutations

Thirty-two, each caught by exactly one check.

1–10 the guards: drop `Ship.canUse`; drop the reach check; drop it on the
server only *(send the command without opening the menu, or this passes)*;
drop the sandbox read; make an absent sandbox value read as *Off*; delete the
`reserve() > 0` summon guard; delete the `crystals() > 0` guard; delete
`takeCrystal()`; take the cure's cost from the reserve instead; delete the
treatment's reserve spend.

11–19 the cure: use one-argument `SetBitten(false)` *(assert the part is not
infected afterwards, not merely that the bite is gone)*; delete per-part
`SetInfected(false)` keeping the body-level one *(tick the body once, or the
latch hides it)*; delete `setInfected(false)` keeping the parts; write
`setInfectionTime(0)`; delete `setInfectionMortalityDuration`; delete
`setIsFakeInfected`; delete the `emhCured` reply *(the moodle survives on the
patient's client)*; delete the `ZOMBIE_INFECTION` reset; delete
`Med.publish` *(the patient's client never sees the parts)*.

20–23 the separation: add `SetBitten` to `Med.TREATMENTS` *(the existing
hypospray check must still fire)*; add the infection clear to `Med.SKIN`; add
it to the EMH's **treat** path; apply `Med.obstructed` to the EMH's `Med.SKIN`
pass *(glass silently stops being treated)*.

24–27 the timer and the model: delete the timer *(the cure lands at once)*;
delete the leave-the-ship check; refund on abort; delete `straighten` at
placement *(assert the yaw **before** any rebuild)*.

28–32 the hologram and the protocol: delete the count-before-placing *(two
Doctors)*; delete the build phase *(`TREK_Rebuild()` leaves none)*; delete the
removal-on-dismiss; delete the offer's expiry; address a reply to the asker
instead of the patient *(**invisible in single player** — this one needs
`emh_multiplayer()`)*.

And the discipline the cooldown keeps breaking: **run the cycle guard out
before every refusal test**, or one guard's deletion is masked by another's
timer — the `cooled()` pattern from `medical()`.

### 13.3 `tests/pz_sim.lua`

| Addition | What silently passes without it |
|---|---|
| **`SetBitten(false)` modelled as infecting the part**, the two-argument form as not | mutation 11 — the worst bug in the feature |
| BodyPart `isInfected` / `isFakeInfected` and their setters | 12, 13, 16 — today only `isBitten` exists |
| **A body tick that re-derives `BodyDamage.isInfected` from the parts** | 12 and 13 both |
| BodyDamage `infectionTime`, `infectionMortalityDuration`, `isFakeInfected` | 14, 15 |
| `Stats` / `CharacterStat.ZOMBIE_INFECTION` | 17, 18 |
| `setHaveGlass`, `setHaveBullet(b, n)` | 23 |
| **`syncBodyPart`**, recording `{part, mask}` per call | 19 — and record the part, not a count, or "synced the first one only" is invisible |
| `ISModalDialog` | the whole consent path |
| `SIM.hurt(p, "infection")` setting **all** the fields at once | a test that infects a body by hand sets only what it later checks |
| `getWorldAgeHours()`, advanceable | 24, 25 |
| `scriptItem("TrekShuttle.TrekEMH", ...)` in the catalogue | "the Doctor is not replicable" is the dilithium blocklist bug verbatim |
| **World items inside `getObjects()`** | 29, and two holes that exist today |

### 13.4 `static()`, and the other suites

Four checks to add, the first a real gap now: **every `deny(player, "reason")`
literal in `server/` has an entry in `TREK_Core.lua`'s `DENIALS`**; no
`client/` file calls `syncBodyPart`; nothing assigns `ISHealthPanel.cheat`; and
a floor on the command count, so a client file that sends nothing cannot pass
the sent-versus-handled check trivially.

- **`test_layout.py`** — `C.EmhSpot` inside the hull, off the pad, carrying no
  layout entry; `C.EmhMenuSpots` all inside the hull; and the cross-fixture
  rule from §3, which all three pass once the core is tightened.
- **`test_assets.py`** — the mesh, the texture, the portrait, the item and
  model blocks, `Tooltip_TREK_EMH`, `ItemName`, every `IGUI_TREK_Emh*` literal
  in the Lua, and the sandbox option in both files with all three value names.
  And while you are there: `Sandbox_TrekShuttle.Replicator_tooltip` still says
  the reserve "refills itself over about eight game hours", which has been
  untrue since dilithium landed.
- **`test_helm.py`** — drive `TREKEMHWindow` for several frames: no throw, no
  draw outside the panel, no label wider than its button, no dead control,
  every button reachable by controller, B closes, focus handed back. Draw it
  once with a long patient name and once with zero crystals.

**Write every check so it cannot pass empty.** Assert
`#Med.TREATMENTS >= 8` and `#Med.CURE >= 4` before iterating them; assert the
*reason* on every refusal, never merely that nothing happened; and put the
"hypospray still does not cure a bite" and "the EMH does" checks through **one
named list of infection fields** in one helper, with a floor on its length, so
the two can never drift apart.

---

## 14. What to check in game

A play-through. The panel shows everything a console report would, and the log
is read afterwards with `sh tools/readtest.sh`.

**In any world built at revision 17 or later** — no fresh world needed:

1. **Beam up, walk aft, right-click the wall panel** beside the biobed. The
   option should read *Consult the Emergency Medical Hologram*, and be there
   and greyed from the far end of the cabin.
2. **He appears.** A figure standing at the square beside the bed, square to
   the ship, lit blue, about the height of the warp core. Look at him from
   both sides. This is the check that cannot be done anywhere but here.
3. **The panel.** He says something. The portrait reads at panel size. Your
   name is in the patient row.
4. **Get hurt properly** — cut, scratched, deep wound, burn, fracture, and
   something with glass in it — and press **Treat**. Everything closes, the
   splint and the dressing come off, the glass comes out, and he says what he
   did. Then the one that matters: **get bitten first, and check the bite is
   still there afterwards, with the infection moodle still on.**
5. **Get bitten and cure it.** The panel should say you are infected — the
   first time anything in this mod has told you. Press **Cure**: one crystal
   goes, the reserve does not move, and he tells you to stay aboard.
6. **Sleep on the biobed.** Wake up: no bite, no infection, **and no infection
   moodle.** Look hardest at the third one.
7. **Do it again and walk out of the cabin halfway through.** It stops, he
   says so, and the crystal is gone.
8. **Empty the core** with the replicator and try again — the refusal names
   dilithium.
9. **Dismiss him**, then `TREK_Rebuild()` while he is up, then beam out and
   back: he should be standing exactly once each time, and never twice.
10. **A controller**: walk the panel with the stick, act with A, close with B,
    and check focus returns to the game.
11. **Sandbox *Off*** in a second world: the option says the station is
    inactive. Then spend the reserve to nothing with the replicator and
    right-click the station — he should not come up at all.

**Then with two people**, on the session pinned in `ROADMAP.md`:

12. one player consults, the other is the patient — **the yes/no appears on
    the patient's screen**, and declining costs nothing;
13. accepting spends one crystal and both panels show the new count;
14. the cure lands on the patient's own machine, moodle included;
15. the hologram is standing on both screens, and goes on both when dismissed;
16. a player not on the crew is refused under *Owner and crew*.


---

## 15. Where the plan met the engine

Everything above is as it was written before the work started. Eight things
came out differently, and each of them is here because the reason generalises
-- six were found by a render or a test that the plan itself called for, which
is the case for calling for them.

### The mesh

- **He came out of the importer facing north.** An image-to-3D model is built
  looking down its own +Z, which this engine reads as due north, so the first
  render had him standing in the sick bay with his back to the entire cabin.
  `import_glb` grew a third parameter, `yaw`, alongside the two §2.3 named,
  and `EMH_YAW = 180` turns him to face south -- the facing every sprite set
  in `C.Sprites` falls back to and the one the isometric camera shows the
  front of.
- **The scanlines could not be texture rows.** §2.2 asks for "horizontal
  scanlines, one pixel in four", and written that way they render as **wood
  grain**: an auto-unwrapped atlas has no horizontal, so a row of the sheet
  is a different diagonal on every patch of him. `gen_emh.py` rasterises the
  mesh's own UVs once to give every texel the *world height* of the surface it
  lands on, and bands on that instead. The intent of the spec is met; its
  arithmetic is not.
- **And they had to be much finer and fainter than they read at 400 pixels.**
  The first working version was a man in a striped prison jumper. The
  generator now also renders him at 96px -- the size he is actually drawn --
  because judging art at ten times its size is how the first gagh shipped as
  a bowl of chili.
- Two tool bugs fell out of the import and are fixed: `import_gltf` wrote the
  glTF's four-byte bufferView padding after the PNG's IEND, and
  `preview_model.parse_x` was silently **dropping the last vertex of every
  mesh it read** -- harmless on a generated mesh whose last vertex no face
  uses, an IndexError on an imported one. It now fails loudly when the count
  it parses does not match the count the file declares.

### The cure

- **`Med.CURE` is a list of questions, not of fixes.** §6.2 says the cure is
  `RestoreToFullHealth()` per part, and that call clears every field in the
  list by direct putfield -- so a `fix` beside each entry was code no mutation
  could distinguish from its own absence (survivors 11 and 12 of the first
  pass). Worse, one of them was a liability: a `SetBitten` call sitting after
  the bundle can only ever put back what the bundle took off. The fixes are
  gone; the asks remain, as the named list §13.4 asks for, and the read-back
  afterwards is what would catch the engine changing.

### The treatment

- **`Med.removeForeign` runs last**, as §6.1 lists it and not first as it was
  first written. With the glass taken out before the skin pass, applying
  `Med.obstructed` to that pass changes nothing at all -- which would have
  made mutation 23 unfalsifiable. The order is the design: he closes the
  wound *and then* takes the shard out.

### The panel

- **A refusal is not a caption.** "The cure needs a whole dilithium crystal,
  and there are none aboard" measures 435 pixels against a 165-pixel button,
  so it was drawn from x = -49 and ran off both ends of the panel. There are
  two tables now: `M.BUTTON_TEXT` in two or three words for the control, and
  `M.REFUSAL_TEXT` in a sentence for the tooltip and the note. Found by
  `tests/test_helm.py`, which is the only thing short of the game that can
  see it.

### The lists

- **`infectedWound` is not in `Med.CURE`.** It went in with the rest of the
  infection fields and it does not belong there: an infected *wound* is an
  ordinary dirty cut, the hypospray cures it by design, and it is one letter
  away in the source from the thing that kills you. The check that a dose
  leaves every `Med.CURE` field alone failed the moment it was written, and
  it was right to -- had the list shipped as it was, the mod would have been
  asserting that the hypospray must not cure an infected cut, which is the
  opposite of what `TREK_Medical.lua`'s own header promises. Four fields,
  which is the floor §13.4 asks for exactly.

### The tests

- **`C.ReplicatorMenuMargin` moved into the config.** §3's cross-fixture rule
  has to read the number the replicator's menu actually uses; a copy of it in
  the test would go stale the first time the menu moved, and the rule it
  enforces is the one that stopped the warp core answering on the Doctor's
  square.
- **The mutation harness runs every suite, not just the protocol one.** Three
  of the first pass's nine survivors were guards whose only observable effect
  is a greyed button, and the suite that draws buttons was not being run.
- **Three survivors were tests that passed for the wrong reason**, and they
  are worth naming because none of them is specific to this feature:

  | | |
  |---|---|
  | The expiry test sent `token = 1` | By then the server had minted three offers, so it was refused as *no such offer* -- which looks exactly like the expiry working. It reads the token off the modal the patient was actually shown |
  | Mutations 20 and 21 appended a line to an existing `fix` | Which inherits that entry's `ask`, so `SetBitten` only ever reached a limb that was in pain and the bitten limb was never touched. They are entries of their own now |
  | A dose was asserted to leave the virus "not set" | Which counts a field nobody ever set. It compares the list before the dose with the list after |
  | The body-level cure assertions ran in single player | Where the patient's own client handler runs *in the same process* and repairs whatever the server left wrong. Three mutations survived behind that. The check moved to `emh_multiplayer`, against the server's own copy -- which is the copy that matters, because the server is the machine that simulates a body |

  The last one is the general lesson and it is new to this mod: **single
  player cannot test a fix that both ends apply.** If the server writes a
  value and the patient's client writes it too, one process makes them
  indistinguishable, and only two can tell which of them is doing the work.
