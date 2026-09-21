# The Emergency Medical Hologram

How the ship's doctor works, how to change him, and what will bite you if you
do.

**Built 2026-09-20 and not yet seen in a game.** *Not built, and still to
settle in game* below is the play-through that is owed. It needs **no fresh
world**: the wall station at 3,3 and the clear square at 2,4 were authored
into the interior by the refit, so `C.BuildRev` 22 is the whole migration and
a cabin built at revision 17 or later gets him on the next arrival. That makes
the Doctor the first system in this mod to reach an existing save.

He is three things at once, and the third is the point of the other two:

- a **model** the server stands on the deck when somebody asks for him;
- a **dialogue panel** that diagnoses and treats, with supplies that never run
  out and a power bill that does;
- **the only cure for zombie infection in this mod.** Nothing else here
  touches a bite. It costs one whole dilithium crystal and twelve in-game
  hours aboard.

`DEV_GUIDE.md` is the general one and its "Rules that exist because they were
broken" all apply here. `MULTIPLAYER.md` is the client/server split,
`MEDICAL_SET.md` is the four instruments whose primitives he inherits, and
`REPLICATOR.md` is the other cabin fixture with a panel behind it. This file
is the Doctor.

---

## What happens when somebody consults him

```
client  right-click one of C.EmhMenuSpots -> "Consult the EMH"
        M.fillMenu greys it, with a reason, for anything E.refusal() says
        M.open -> emhSummon (only if he is not already up) + TREKEMHWindow

server  Net.onServer("emhSummon")
        atEMH: alive / Ship.canUse / sandbox / reach, all on its own copy
        s.emh = true; Ship.commit(); B.serviceEMH()

every   Ship.onChange -> s.emh flipped -> each client hangs its own light
client  and plays TREK_EmhAppear once. Scenery, never ship state.

client  the panel reads YOUR body directly, every frame
        for anybody else: emhLook { who } -> emhFindings { ... }
        (a remote body does not exist on a client to be read -- see below)

client  Treat / Cure
        yourself     -> straight through
        anybody else -> the server mints a token and raises a yes/no on
                        THEIR screen (emhOffered), never on yours

server  treat:  Power.afford(C.EmhTreatCost) -> spend
                Med.treatWith(TREATMENTS) -> Med.treatWith(SKIN, unskipped)
                -> Med.removeForeign -> Med.publish (syncBodyPart per part)
        cure:   Power.takeCrystal() NOW, s.emhCures[name] = worldHours + 12

server  EveryOneMinute -> S.serviceCures
        left the ship -> drop it, tell them, the crystal is gone
        due          -> Med.cure (parts) + the BodyDamage flags + emhCured
        offline      -> leave it; the register is ship state and is saved

client  emhCured -> clear your own BodyDamage flags and the infection moodle,
        because syncBodyPart carries BodyPart fields ONLY
```

Four orderings in there are deliberate and easy to break:

- **The skin pass runs before the foreign bodies come out**, and unskipped.
  That is the whole difference between the Doctor and the regenerator in your
  pocket, which refuses to close skin over a shard. Take the glass out first
  and applying `Med.obstructed` to his pass would change nothing at all.
- **The crystal is spent when the cure starts, not when it lands.** It is a
  commitment rather than a reservation, and that is the entire weight of the
  twelve hours.
- **Nothing is spent when an offer is made.** The token is a question.
  Everything is re-validated when the answer comes back, because in between
  the asker can walk away, the core can be emptied and the patient can leave.
- **The body-level flags and the moodle are cleared at both ends.** The server
  writes its copy and the patient's own client writes theirs. In single player
  those are one process, which is exactly why that is easy to get wrong — see
  *What would have bitten you*.

---

## Where everything lives

| File | What it holds |
|---|---|
| `shared/TREK/TREK_EMH.lua` | where he stands, who is in reach, who may be a patient, the sandbox, and **`E.refusal()` — the one copy of the rules**, so the panel greys for exactly the reason the server refuses |
| `shared/TREK/TREK_Medical.lua` | `Med.CURE` (the named infection fields), `Med.cure`, `Med.removeForeign`, `Med.publish` |
| `shared/TREK/TREK_Config.lua` | every constant — section *The Emergency Medical Hologram* — and his line in `C.ReplicatorBlocked` |
| `server/TREK/TREK_Server.lua` | the seven handlers, the consent register, `S.beginCure`, `S.serviceCures`, `S.emhReport` |
| `server/TREK/TREK_Build.lua` | `B.emhAt`, `B.serviceEMH`, `B.emhReport`, and the `emh` build phase |
| `client/TREK/TREK_EMHUI.lua` | the menu, `TREKEMHWindow`, the light, the consent prompt, the replies |
| `client/TREK/TREK_Core.lua` | his eleven `DENIALS` lines |
| `media/scripts/trekshuttle.txt` | `item TrekEMH`, `model TrekEMHModel`, `sound TREK_EmhAppear` |
| `media/sandbox-options.txt` | `TrekShuttle.EMH` — Full or Off |
| `lua/shared/Translate/EN/` | `IG_UI.json` (his voice and every refusal), `ItemName.json`, `Tooltip.json`, `Sandbox.json` |
| `tools/gen_emh.py` | the mesh, the texture, the portrait, the chime **and the renders it is judged on** |
| `tools/assets/trek_emh/` | the vendored GLB and `SOURCE.txt` — the raw, so regenerating needs no network |
| `design/art/emh/` | the concept image and three renders, including one at the size he is actually drawn |
| `tests/test_multiplayer.py` | the `emh()` and `emh_multiplayer()` scenarios |
| `tests/test_helm.py` | `TREKEMHWindow` drawn, twice, for a well patient and a wrecked one |
| `tests/pz_sim.lua` | `SetBitten`'s trap, the infection latch, `syncBodyPart`, `ISModalDialog`, the world clock |

**Nothing is in the `.tbx`.** The station and the square were authored by the
refit before he existed, which is why this feature is cheap in the cabin and
expensive only in art.

### State

One field in the ship state, and one register beside it.

```lua
s.emh      = true | nil      -- he is up. Ship state: every client sees the
                             -- same figure standing on the deck
s.emhCures = { [username] = <world age in hours when it completes> }
```

**`s.emh` is cleared in `OnInitGlobalModData`**, beside the block that clears
`s.flying`. A hologram does not survive a world reload, and clearing it
deletes the entire class of stale-flag bug. **`s.emhCures` is kept**: a cure
in progress has been paid for with a crystal and has to survive a relog.

`s.emhCures` is a table inside a state that is transmitted whole on every
change, which `DEV_GUIDE.md` warns about by name. It is allowed here because
it is bounded by the number of people **simultaneously under treatment**, each
entry is one number, and entries are removed the moment they complete or are
abandoned. It is not a log and it must never become one.

**There is no cooldown.** Treatment does nothing to a healthy patient and the
cure takes twelve hours, so a held button is already its own limit; a cycle
guard here would be the cooldown-wearing-a-hat that `REPLICATOR.md` threw out
by name.

### The protocol

```
client -> server            server does
  emhSummon                 stands him up at 2,4, s.emh = true
  emhDismiss                takes him down, s.emh = nil
  emhLook   { who }         reads that patient's body and reports back
  emhTreat  { who }         treats, or offers if `who` is somebody else
  emhCure   { who }         cures, or offers
  emhAccept { token }       the patient agreeing
  emhDecline{ token }

server -> client
  emhFindings{ who, total, infected, bitten, items }   to the ASKER
  emhOffered { token, from, what, cost }               to the PATIENT
  emhTreated { who, counts, total }                    to the patient
  emhCureStarted { hours }                             to the patient
  emhCured   { }            to the patient: clear your own body-level flags
  emhCureLost{ }            to the patient: you left, and so did the crystal
  denied     { why, ... }   to whoever asked
```

**`emhLook` is not a convenience.** In multiplayer a remote player's body
damage does not exist on a client to be read, so the panel cannot work out
what is wrong with the crewman on the biobed by itself. For yourself it reads
your own body directly and sends nothing.

**There is no `emhDiagnose`.** Opening a health panel on a body is client UI
and the sandbox is readable in every process; a handler whose only job is to
answer "yes" is a round trip that can drift out of step with the panel that
calls it.

---

## Changing it

### What he costs

```lua
C.EmhTreatCost    = 25    -- reserve units, so 200 treatments to a crystal
C.EmhCureCrystals = 1     -- whole crystals, not units
C.EmhCureHours    = 12    -- in-game hours aboard
```

**Supplies are infinite; power is not.** There is nothing to restock, no doses
and no dressings — which is what `ROADMAP.md` asks for — and the limit is the
same dilithium the replicator burns. He will not come up at all on an empty
reserve with no spares, which is what four separate comments in this
repository promised before he existed: *"a crew with no crystals has a galley
fixture and a hologram that will not switch on."*

At 25 against a crystal's 5000 a treatment is unlimited in play and still
honest about what it runs on. If you raise it far enough to matter, raise it
knowing the refusal a player meets is `emhNoPower`, which sends them looking
for dilithium rather than telling them the mod is broken.

### The cure, and the twelve hours

Per part, **`part:RestoreToFullHealth()`** — a deliberate inversion of
`DEV_GUIDE.md`'s rule about convenience methods. That rule forbids it to the
hypospray *because* it clears the bite; the EMH is the one thing in this mod
that may, and the disassembly says the short call is also the **safe** one
here: thirty-seven fields by direct putfield, no call to `SetBitten` anywhere,
so it cannot spring the trap that method is.

Then, once, on the character, on the server:

```lua
damage:setInfected(false)
damage:setIsFakeInfected(false)
damage:setReduceFakeInfection(false)
damage:setInfectionTime(-1.0)                 -- -1, NOT 0
damage:setInfectionMortalityDuration(-1.0)
```

**Both levels, in one pass.** `BodyDamage.isInfected` is a one-way latch
re-derived from the parts every tick and *skipped* once true: clearing it
alone is undone next tick, and clearing the parts alone never clears it.

Then `Med.publish(patient)` and `Net.toClient(patient, "emhCured", {})`. That
last message is **not optional** — `syncBodyPart`'s mask carries `BodyPart`
fields only, so the flags above and the infection moodle do not ride it, and
the patient's own client clears them itself.

**`Med.CURE` is a list of questions, not of fixes**, and that is the one thing
about it worth knowing. `RestoreToFullHealth` clears every field in it in a
single call, so a `fix` beside each entry would be code no test could tell
from its own absence — and one of them would be actively dangerous. It is the
named list `medical()` and `emh()` both walk, so the hypospray's promise and
the Doctor's reason to exist cannot drift apart, and `Med.cure` asks every one
of them again afterwards and warns about anything still set.

**`infectedWound` is deliberately not in that list.** An infected *wound* is
an ordinary dirty cut, the hypospray cures it by design, and it is one letter
away in the source from the thing that kills you.

The timer is ship state and the register is walked on `EveryOneMinute`:
leaving the cabin drops the entry and **does not refund the crystal**. Both
halves of the biobed carry `BedType = goodBed`, so a patient can sleep it off;
on a server they cannot, and twelve game hours at the default day length is
about half an hour confined to the cabin. That is the cost, and it is
deliberate.

### What a treatment does

```lua
Med.treatWith(patient, Med.TREATMENTS)   -- the hypospray's list
Med.treatWith(patient, Med.SKIN)         -- the regenerator's, UNSKIPPED
Med.removeForeign(patient)               -- glass and bullets, last
Med.publish(patient)
```

`Med.SKIN` is applied **without** `Med.obstructed`: the regenerator refuses to
close skin over glass, and the Doctor closes it and then takes the glass out,
which is the whole reason he is better than the instrument in your pocket.
Reversing those last two lines makes that difference untestable.

`Med.removeForeign` is two setters per part and the second takes two
arguments:

```lua
part:setHaveGlass(false)
part:setHaveBullet(false, 0)        -- (boolean, int). One argument throws.
```

**Treatment leaves a bite and the zombie infection exactly where it found
them.** The hypospray's six-dose limit, the regenerator's scope and the reason
the EMH exists all rest on the bite being the one thing you come home for.
Nothing in the treat path touches `Med.CURE`.

### Who may be a patient, and consent

**Anyone aboard.** The panel lists everyone in the cabin; the server resolves
the patient from its **own** copy of where people are standing and refuses
anyone who is not there. A client is a request, never a fact, including about
whose body it is.

Treating yourself needs no consent. Treating anybody else mints a token,
raises an `ISModalDialog` on **their** screen naming who is asking and what it
costs, and re-validates everything from scratch when the answer comes back.
The offer expires (`C.EmhOfferMs`) and is single-use.

**Nobody can force-heal — or force-anything — another player.** That is the
padlock-and-safehouse rule from `MULTIPLAYER.md` applied to bodies. In single
player the offer path never runs, so it is only ever exercised by
`emh_multiplayer()`.

### Where he is in the ship

```lua
C.EmhStation   = { x = 3, y = 3 }   -- the wall panel, authored in the .tbx
C.EmhSpot      = { x = 2, y = 4 }   -- where he stands
C.EmhMenuSpots = { {2,3}, {3,2}, {3,3}, {2,4}, {3,4} }
C.EmhRange     = 2                  -- the replicator's and the core's
```

`industry_01_15`, tag `emhPanel`, is from the hull's own wall set and carries
neither `solid` nor `solidtrans` — so 3,3 is still deck. Deliberately **not** a
light switch: every `lighting_indoor_01` switch carries the `lightswitch` tile
property, and a mod button that turns into a real `IsoLightSwitch` on the next
world load is a bug that only appears in somebody else's save.

A right-click resolves to the **floor square under the cursor** and he is a
tall model, so the menu answers on a named set rather than one square. A
*named set*, not a box: the warp core's menu used to be a one-square box
around 1,3, which reaches 2,4, so walking up to the Doctor offered to load a
dilithium crystal into a hologram. It is `C.CoreMenuSpots` now, and
`tests/test_layout.py` holds the rule for all three fixtures — **no fixture's
menu squares may contain another fixture's own square, or the transporter
pad.** The replicator's margin lives in `C.ReplicatorMenuMargin` so that rule
reads the number the menu actually uses rather than a copy of it.

### Standing him up and taking him down

`B.serviceEMH()` makes the deck match `s.emh`, **idempotent in both
directions**, so it is safe from a summon, a dismissal, a build and the
per-minute tick. Five things it has to do, each of which has already cost this
project a bug elsewhere:

1. **Count before placing.** A world item is saved and `U.clearSquare`
   deliberately preserves world items, so a pass that does not look first
   stands a second Doctor there every time it runs — and it runs every game
   minute.
2. **Remove all of them, not the first.**
3. **Straighten.** `IsoWorldInventoryObject`'s constructor writes
   `Rand.Next(0, 360)` into an unset yaw. On placement *and* on every later
   pass, because that later pass is the only thing that will ever reach a
   crooked Doctor in an existing save.
4. **Run as a build phase**, beside `furnishReplicator` and `furnishCore` —
   not only on the timer. `B.forceRebuild` wipes everything but the floor, so
   `TREK_Rebuild()` really does delete him while `s.emh` still says he is up.
5. **Use `removeWorldItem(sq, fullType)`** through `removeSynced` →
   `transmitRemoveItemFromSquare`. `removeWorldObject` throws on a server.

**There is no ghost list, and that is worth knowing why.** A hull that could
not be removed has to be *remembered*, because nothing else will ever go back
and look. A Doctor left standing in an unloaded chunk is simply a disagreement
with a flag, and the next pass over a loaded cabin settles it.

### The panel

`TREKEMHWindow`, an `ISPanelJoypad` built from the helm's own LCARS parts
(`H.pill`, `TREKLcarsButton`, `H.P`), so the ship's third console does not look
like a third mod.

**It is a dialogue, not a control panel**, and that is a requirement rather
than a flourish. He speaks: a line at the top that changes with what he has
been asked and what he found, above his portrait. Every action is a thing he
says he is doing and then a thing he reports having done — which is also,
usefully, the only way a player can tell a treatment that worked from one that
was refused in silence.

| Part | What it shows |
|---|---|
| Portrait | `media/ui/TREK_EmhPortrait.png`, rendered from the same mesh and texture he is, so the two cannot drift apart |
| His line | one or two sentences from `IGUI_TREK_Emh*`, chosen by state |
| Patient | a stepper over everyone aboard; you are first and selected by default, and it is dead when there is only you |
| Findings | itemised, from the same lists the treatment walks — so the readout cannot drift from what the button does |
| Infection | **whether they are carrying it** — the one thing the medical tricorder deliberately will not say |
| Reserve and crystals | what a treatment costs and what a cure costs |
| **Treat** | greyed, with a reason, when there is nothing to treat |
| **Cure the infection** | greyed, with a reason, when they are not infected or the core is empty |
| **Full readout** | `M.openHealthPanel` — vanilla's `ISHealthPanel` at `C.MedDoctorLevel`. Never `ISHealthPanel.cheat` |
| **Dismiss** | takes him down |

Opening the panel sends `emhSummon` if he is not already up; *Dismiss* sends
`emhDismiss`. **Closing the window does neither** — a crewman closing his own
panel must not take the Doctor away from somebody else at the biobed.

Shown-and-greyed, never hidden; the panel closes itself when the player walks
out of reach (`ISFeedingTroughUI:prerender` is vanilla's precedent).

Two things about the labels. A refusal is **not a caption**: there are two
tables, `M.BUTTON_TEXT` in two or three words for the control and
`M.REFUSAL_TEXT` in a sentence for the tooltip and the note, because "The cure
needs a whole dilithium crystal, and there are none aboard" measures 435
pixels against a 165-pixel button. And the roster is read **once a frame** —
`E.patients()` walks `getOnlinePlayers()`, and `prerender` is the only place it
is recomputed.

### His model

`C.EmhHeight = 1.25` tiles, fitted by **height**. The warp core is 1.30 and
stands in a passage the crew walk down; a person is a shade shorter than the
ship's power plant. The number to trust is the **bounding box `gen_emh.py`
prints**, not the constant — `DEV_GUIDE.md`'s bat'leth lesson, where
`SPAN = 0.46` drew 0.531.

```sh
python tools/gen_emh.py TrekShuttle/42
```

writes the mesh, the texture, the portrait, the chime and three renders, and
is **deterministic** — no randomness anywhere, so re-running writes
byte-identical files and a regenerated asset is never a silent diff.

The figure itself is **vendored, not generated**: `tools/assets/trek_emh/`
holds the GLB with a `SOURCE.txt` naming the model, the date, the seed and the
prompt. Re-running fal gives a *different* figure, not the same one again, so
the GLB is the raw — the convention `tools/assets/type6_shuttle/` set and the
reason `import_quaternius.py`'s header gives: **regenerating the mod must not
require network access, Blender or a third-party package.**

What makes him a hologram rather than a mannequin is entirely in the texture,
and all of it is under our control:

- **one hue** — luminance-mapped onto the LCARS blue ramp (`H.P.blue`), because
  a monochrome figure cannot read as a shop dummy the way a flesh-toned one
  can;
- **scanlines**, banded in **world height** rather than in texture rows (see
  *What would have bitten you*);
- **a lifted floor**, so the darkest parts glow rather than going black
  against a dark deck.

`import_glb` grew three additive parameters for him — `target_height`, `name`
and `yaw` — and the hull's call site is byte-identical, which
`tests/test_assets.py` would notice if it were not.

### His voice and likeness

He is the **Emergency Medical Hologram**, a descriptive designation, not a
named character. His lines are written for this mod — dry, impatient,
competent — and not quoted from the show; the famous one is not his signature
line here. There is no speech audio and no imitated voice: the summon sound is
a synthesised chime from `gen_emh.py`'s own oscillators, like the medical
set's three. Nothing in `design/art/emh/` is derived from a frame of anything,
and the concept prompt describes a uniform and a stance, never a person — the
first generation came back wearing a Starfleet delta and was thrown away for
it.

`ROADMAP.md` sets the standard — *"is it Star Trek without copying a frame of
the show"* — and this is the feature where it bites.

### The sandbox

`TrekShuttle.EMH`, two values, default 1:

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

## The rules it obeys

Not optional; `MULTIPLAYER.md` has the reasoning.

- **Every body is written on the server and nowhere else**, and that is forced
  by the engine rather than chosen. `BodyDamage.Update()` decides who
  simulates a body at bci 21–62: not a client, run the whole simulation; a
  client with its own body, return; a client with somebody *else's* body,
  `RestoreToFullHealth()` it. So a remote player's body on a client is wiped
  clean every single tick. The server is not a better place to treat somebody
  from — it is the only machine that knows they are hurt.
- **A client is a request, never a fact**, including about who the patient is.
  Every command re-resolves the patient from the server's own view.
- **One copy of the rules.** The panel greys a control and the server refuses a
  command from the same `E.refusal()`, so they cannot disagree.
- **The hologram is ship state; the light is not.** Everyone aboard sees the
  same figure because `s.emh` is committed; each client hangs its own
  `addLamppost` and plays its own chime, which is the same documented
  exception the cabin's lamps and the torpedo's light already use.
- **No admin-only or `-debug`-gated calls.** `panel.doctorLevel` on the
  instance, never `ISHealthPanel.cheat`.

| | |
|---|---|
| The hologram standing on the deck | **Server**, `s.emh`, placed and removed as a world item |
| Who may use him | **Server** — alive, `Ship.canUse`, the sandbox and the reach, on its own copy |
| Who the patient is | **Server**, from its own copy of who is aboard. Never sent by a client |
| Consent | **The patient's client** raises it; the server mints, expires and re-validates the token |
| **The body** | **Server**, written directly, pushed with `syncBodyPart` |
| The body-level infection flags and the moodle | **The patient's client**, on `emhCured`, because the packet does not carry them |
| The crystal and the cure register | **Server**, ship state, one writer |
| The light at 2,4, the panel, the portrait | **Each client, for itself.** Scenery and presentation |

---

## Engine facts, established

With `tools/pzapi.py` (exists, public), a grep of vanilla Lua for a call site
whose path is **not** `AdminPanel/` or `DebugUIs/` (may I call it), and
`tools/javadis.py` (**under what condition** — the one that matters). Do not
re-derive these.

| Fact | Where |
|---|---|
| **`BodyPart.SetBitten(boolean)` — one argument — infects the part.** The guard ends at bci 102; `isInfected = true` and `generateBleeding()` follow unconditionally | `javadis.py` |
| **`SetBitten(false, false)` is correct** — bci 33 `iload_1; ifeq -> 105` puts the whole block behind the guard | `javadis.py` |
| Vanilla's admin health cheat uses the broken form, twice | `ClientCommands.lua:490`, `ISHealthPanel.lua:222` |
| **`BodyDamage.isInfected` is a one-way latch**, re-derived from the parts each tick (bci 280–300) and **skipped once true** (bci 271). Both levels must be cleared in one pass | `javadis.py` |
| **`RestoreToFullHealth()` writes 37 fields by putfield and never calls `SetBitten`** — right for the cure, wrong everywhere else in this mod | `javadis.py` |
| **`getInfectionTime() < 0` is the "not started" sentinel** — `Update()` bci 371–377. Write `-1.0` | `javadis.py` |
| **The infection moodle freezes rather than clearing**: the countdown is gated on `isInfected()` and is the stat's only writer | `javadis.py` |
| `setHaveGlass(boolean)`; **`setHaveBullet(boolean, int)`** | `ISRemoveGlass.lua:73`, `ISRemoveBullet.lua:69` |
| `Capability.CanMedicalCheat` gates only added pain, instant completion and the consent bypass — **not** the foreign-body setters | `ISRemoveGlass.lua:66,83` |
| **`syncBodyPart(part, mask)` returns unless `GameServer.server`**, then sends `BodyPartSync` to that one player's own connection. Ten vanilla call sites, all under `shared/TimedActions/` | `javadis.py`, `ISApplyBandage.lua:148` |
| Its mask is **42 bits**; `0xFFFFFFFFFFF` is "everything", which is what vanilla passes | `javadis.py`, `ClientCommands.lua:596` |
| **It carries `BodyPart` fields only** — `BodyDamage` flags and the `Stats` moodle do not ride it | `javadis.py` |
| `getGameTime():getWorldAgeHours()` is public with non-debug call sites | `ISButtonPrompt.lua:520`, `WinterIsComing.lua:8` |
| `ISModalDialog:new(x, y, w, h, text, yesno, target, onclick, player, p1, p2)`; `onclick(target, button, p1, p2)` with `button.internal` = `"YES"`/`"NO"` | `ISTradingUI.lua`, `ISInventoryPane.lua`, `ISPostDeathUI.lua` |
| `character:playSound(String)` is reachable for an ordinary player | `FishingStates.lua:91`, `ISBuildAction.lua:217` |
| `CharacterStat.ZOMBIE_INFECTION` appears only under `DebugUIs/`, so it is wrapped in `U.try` — but `getStats():set(CharacterStat.X, v)` itself has ordinary call sites | `ISAnimalContextMenu.lua:739`, `AReallyCDDAy.lua:70` |
| `cell:addLamppost(x, y, z, r, g, b, radius)` returns the light; `removeLamppost(light)` takes that object, not a position | this mod, `TREK_Torpedo.lua:180-194` |
| `panel.doctorLevel` on the instance opens every Doctor gate; `ISHealthPanel.cheat` is `false or getDebug()` | `MEDICAL_SET.md` |
| **No vanilla humanoid model is static** — every one is `static = false` with an `animationsMesh`, so none can be borrowed as a `WorldStaticModel`. The mod makes its own | `scripts/generated/models_characters.txt` |
| `import_glb` handles glTF Y-up, smooths normals, and takes one embedded PNG diffuse texture | `tools/import_gltf.py` |

---

## Testing

`tests/test_multiplayer.py::emh()` plays it **through the menu and the panel**,
never by calling a handler — driving a handler passes against a build whose
button is wired to nothing, which is how the torpedoes once shipped unfireable
and the replicator once shipped un-right-clickable. It covers: the option at
the station and greyed from across the cabin, with the reason on it; the
server refusing the same thing without the menu ever being opened; one Doctor
standing square, **counted before anything rebuilds**; three service passes
leaving one; a treatment clearing both lists plus the glass and the bullet and
the wound *under* the glass, and leaving the bite and the infection exactly as
it found them; the cure taking one crystal and not touching the reserve; the
cure not landing early and landing on time; every per-part and body-level
field checked one at a time, then the body **ticked** to catch the latch; the
moodle; a cure that did not work reporting so; the refusal naming dilithium;
leaving the ship costing the crystal; `TREK_Rebuild()` deleting him and the
build phase putting him back; dismissal; a crooked Doctor squared up; and both
sandbox values.

`emh_multiplayer()` covers what single player cannot show: both machines
seeing one Doctor, the yes/no on the **patient's** screen and nowhere else,
declining costing nothing, accepting treating them on the server and pushing
**every** body part back, the server's own copy of the body-level flags after
a cure, a lapsed offer, a forged patient, and a stranger refused under
*Owner and crew*.

`tests/test_helm.py` draws the panel for a well patient and a wrecked one, with
a long name and an empty core, and checks every control is on the stick.
`tests/test_layout.py` holds the cross-fixture menu rule. `tests/test_assets.py`
checks the mesh, texture, portrait, sound and every string.

**Thirty-two mutations, one pass at a time, all caught.** The runner is not in
`tools/` — write one in the scratchpad, and make it run **every** suite: three
of the first pass's nine survivors were guards whose only observable effect is
a greyed button, and the suite that draws buttons was not being run. Hash the
files before and after; two overlapping runs share them, and this repository
has already shipped `if false then` in a refusal under a green suite.

**Write every check so it cannot pass empty.** `#Med.TREATMENTS >= 8`,
`#Med.SKIN >= 8` and `#Med.CURE >= 4` are asserted before anything iterates
them, and the "a dose leaves the EMH's fields alone" check compares the list
**before** the dose with the list after — a field nobody ever set is not
evidence.

---

## What will bite you

- **No hot reload.** Mod Lua loads when a world starts, and `.txt` script
  changes too. Every change needs a full restart.
- **`SetBitten(false)` — one argument — infects the limb**, and vanilla's own
  admin health cheat calls it that way twice. Use the two-argument form, or
  `RestoreToFullHealth()`, which calls neither.
- **`setInfectionTime(0)` leaves a running clock.** `Update()` only
  initialises the countdown when the value is negative. Write `-1.0`.
- **`setHaveBullet(false)` throws.** It is `(boolean, int)`.
- **`syncBodyPart` is a no-op off the server.** Called from `client/` it looks
  like a sync and is nothing; `static()` forbids it there.
- **`B.forceRebuild` deletes him** while `s.emh` still says he is up. The build
  phase is what repairs it, and a test must assert the *placement* before
  anything rebuilds — otherwise it is checking the repair.
- **Single player collapses the server and the client into one process**, so a
  field both ends write looks correct however badly the server half is broken.
- **Read the result back.** `Med.cure` asks every field again and warns;
  `B.emhReport` prints what the ship believes against what is standing there.
  `TREK_EMH()` from the console is the one line that tells them apart.
- **A right-click lands on the floor, not on the picture.** Anything keyed to a
  tall model needs a named set of squares, and that set must not reach another
  fixture's own square.

---

## Not built, and still to settle in game

Nothing here has been seen in the game. The panel shows everything a console
report would, and the log is read afterwards with `sh tools/readtest.sh`.

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

## What would have bitten you

Kept because each generalises, and `DEV_GUIDE.md` cites three of them as the
cases that produced its rules. Six of the eight were found by a render or a
test that the plan itself called for, which is the argument for calling for
them.

### A vanilla call site proved the wrong thing

`part:SetBitten(false)` is the obvious way to cure a bite. It is public, it
reads exactly like what it says, and **vanilla's own admin health cheat calls
it that way in two places**. Every test this repository knows how to write
would have passed.

Its bytecode writes `bittenZ` from the argument and then runs on regardless:
`isInfectedZ = 1` and `generateBleeding()`. A player who paid a dilithium
crystal and slept twelve game hours would have woken up infected, on an arm
that was now bleeding, with the mod reporting a successful cure and the log
silent.

**A vanilla call site is evidence about reachability and nothing else.** It
says the global resolves and the engine accepts the arguments; it says nothing
about whether the author of that call site wanted what you want — and an admin
cheat wants the limb bitten-and-infected, because it is about to restore the
whole body anyway.

### He faced north

An image-to-3D model is built looking down its own +Z, which this engine reads
as due north. The first render had him standing in the sick bay with his back
to the entire cabin. `import_glb` takes a `yaw` now.

Nothing about an imported mesh was *decided*, which is the general point: the
hull got the same treatment and cost four faults before the game was ever
involved. **Render it and look.**

### The scanlines rendered as wood grain

The plan asked for "horizontal scanlines, one pixel in four", and written that
way they are not horizontal at all: an auto-unwrapped atlas has no horizontal,
so a row of the sheet is a different diagonal on every patch of him, and at
1024 texels over a figure 1.25 tiles tall the pitch aliases into moiré as
well. The first render was a man in a fingerprint.

`gen_emh.py` rasterises the mesh's own UVs once to give every texel the
**world height** of the surface it lands on, and bands on that. Anything that
has to be level, plumb or aligned on an imported model needs the same.

And the first version that worked was a man in a striped prison jumper, judged
at 400 pixels. The generator renders him at 96 now — the size he is actually
drawn — because judging art at ten times its size is how the first gagh
shipped as a bowl of chili.

### A belt that could only ever undo the braces

`Med.CURE` shipped as a list of `ask`/`fix` pairs beside
`RestoreToFullHealth()`. That call clears every field in the list by direct
putfield, so no mutation could distinguish the fixes from their own absence —
and one of them, `SetBitten`, sitting *after* the bundle, could only ever put
back what the bundle had just taken off.

`DEV_GUIDE.md`'s rule for a branch a mutation cannot break is to delete it or
write the test, and there is no honest test for a fallback that runs only if
the engine stops matching its own bytecode. The fixes are gone; the read-back
stands in their place, and a test that makes one part's
`RestoreToFullHealth` a no-op proves the read-back fires.

### The list conflated two infections

`infectedWound` went into `Med.CURE` with the rest, and it does not belong
there: an infected *wound* is an ordinary dirty cut and the hypospray cures it
by design. The check that a dose leaves every `Med.CURE` field alone failed
the moment it was written, and it was right to — had the list shipped as it
was, the mod would have been asserting that the hypospray must not cure an
infected cut, which is the opposite of what `TREK_Medical.lua`'s own header
promises.

### Single player could not see half the cure

The body-level flags are written twice on purpose: the server clears them, and
the patient's own client clears them again on `emhCured`, because
`syncBodyPart` does not carry them. **In single player those are one
process** — `Net.toClient` runs the handler directly — so three mutations that
deleted the server's half entirely left a green suite, because the client
repaired every one of them a millisecond later.

The rule is narrower and more useful than "test it in multiplayer": whenever
two processes both write the same field, single player proves only that
*somebody* wrote it. The assertion has to name the process, which is why
`emh_multiplayer()` reads the **server's own copy** of the patient after a
cure.

### Three tests that passed for the wrong reason

| | |
|---|---|
| The expiry test sent `token = 1` | By then the server had minted three offers, so it was refused as *no such offer* — which looks exactly like the expiry working. It reads the token off the modal the patient was actually shown |
| Two mutations appended a line to an existing `fix` | Which inherits that entry's `ask`, so `SetBitten` only ever reached a limb that was in pain and the bitten limb was never touched. They are entries of their own now |
| A dose was asserted to leave the virus "not set" | Which counts a field nobody ever set. It compares the list before the dose with the list after |

### A refusal is not a caption

"The cure needs a whole dilithium crystal, and there are none aboard" measures
435 pixels against a 165-pixel button, so it was drawn from x = −49 and ran off
both ends of the panel. Two tables now: short for the control, the sentence
for the tooltip and the note. Found by `tests/test_helm.py`, which is the only
thing short of the game that can see it.
