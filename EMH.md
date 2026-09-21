# Emergency Medical Hologram developer guide

This document explains how to maintain, test, and troubleshoot the shuttle's
Emergency Medical Hologram. It describes the **current implementation**, not the
sequence used to build it.

Read these first when changing adjacent systems:

- `DEV_GUIDE.md` — repository workflow, engine constraints, and verification
  rules.
- `MULTIPLAYER.md` — server authority, requests, replies, and world sync.
- `MEDICAL_SET.md` — shared treatment primitives and medical engine behavior.
- `REPLICATOR.md` — the other powered cabin system and its dilithium economy.

The EMH consists of three related parts:

1. a permanent custom projector station mounted in sick bay;
2. a summoned Doctor model projected directly below that station;
3. a server-authoritative medical service, including the mod's only cure for
   zombie infection.

The station and Doctor deliberately share cabin offset **`(3,3)`**. The station
mesh is shallow and elevated against the east bulkhead, leaving the deck clear
for the hologram. The old Doctor position at `(2,4)` and the old
`industry_01_15` wall fitting are migration inputs only and must never be used
for new placement.

---

## Quick verification

After changing EMH code or assets, run:

```sh
python tools/gen_emh.py TrekShuttle/42
python tools/luacheck.py TrekShuttle/42/media/lua
python tests/test_assets.py
python tests/test_stock.py
python tests/test_layout.py
python tests/test_helm.py
python tests/test_multiplayer.py
python tools/deploy_windows.py
```

The generator should report both models:

- `TREK_EMH.x`
- `TREK_EMHStation.x`

The deployed mod must contain all four world-model files:

```text
42/media/models_X/TREK_EMH.x
42/media/textures/TREK_EMH.png
42/media/models_X/TREK_EMHStation.x
42/media/textures/TREK_EMHStation.png
```

Project Zomboid has no hot reload. Fully restart the game after every Lua,
script, model, or texture change. The cabin rebuild is lazy, so beam aboard
before deciding that a revision change did nothing.

---

## Authoritative files

| File | Responsibility |
|---|---|
| `TrekShuttle/42/media/lua/shared/TREK/TREK_Config.lua` | Item IDs, station and Doctor coordinates, menu squares, range, costs, duration, light, sandbox values, and build revision |
| `TrekShuttle/42/media/lua/shared/TREK/TREK_EMH.lua` | Shared eligibility rules, patient lookup, reach checks, findings, and refusal reasons |
| `TrekShuttle/42/media/lua/shared/TREK/TREK_Medical.lua` | Treatment lists, infection fields, cure, foreign-body removal, and body-part publishing |
| `TrekShuttle/42/media/lua/server/TREK/TREK_Build.lua` | Permanent station placement, Doctor placement/removal, legacy cleanup, deduplication, straightening, rebuild repair, and diagnostics |
| `TrekShuttle/42/media/lua/server/TREK/TREK_Server.lua` | EMH commands, consent offers, treatment, cure scheduling, crystal spending, and completion |
| `TrekShuttle/42/media/lua/client/TREK/TREK_EMHUI.lua` | Context menu, LCARS dialogue window, portrait, local light, sounds, consent prompt, and client-side infection-display cleanup |
| `TrekShuttle/42/media/scripts/trekshuttle.txt` | Doctor and station item/model declarations and summon sound |
| `TrekShuttle/42/media/lua/shared/Translate/EN/IG_UI.json` | Dialogue, buttons, findings, and refusals |
| `TrekShuttle/42/media/lua/shared/Translate/EN/ItemName.json` | Doctor and projector-station item names |
| `TrekShuttle/42/media/lua/shared/Translate/EN/Tooltip.json` | Item tooltips |
| `TrekShuttle/42/media/lua/shared/Translate/EN/Sandbox.json` | Sandbox option labels and tooltips |
| `TrekShuttle/42/media/sandbox-options.txt` | EMH Full/Off setting |
| `tools/gen_emh.py` | Deterministic Doctor and station asset generation, portrait, chime, and preview renders |
| `tools/assets/trek_emh/` | Vendored Doctor GLB and source record |
| `design/art/emh/` | Source art and generated review renders |
| `design/buildinged/TrekShuttle_Interior.tbx` | Cabin furniture source; the EMH square must contain no authored appliance panel |
| `tests/test_layout.py` | Shared station/Doctor square and fixture-menu separation |
| `tests/test_helm.py` | EMH panel drawing, labels, disabled states, and controller navigation |
| `tests/test_multiplayer.py` | Station lifecycle, migration, Doctor lifecycle, treatment, cure, consent, authority, and replication |

Do not add a second placement path. The station and Doctor are world items
managed by `TREK_Build.lua`; they are not entries in
`TREK_InteriorLayout.lua`.

---

## Current constants

The relevant configuration is grouped under **The Emergency Medical
Hologram** in `TREK_Config.lua`:

```lua
C.EmhItem        = "TrekShuttle.TrekEMH"
C.EmhStationItem = "TrekShuttle.TrekEMHStation"

C.EmhStation    = { x = 3, y = 3 }
C.EmhSpot       = { x = 3, y = 3 }
C.LegacyEmhSpot = { x = 2, y = 4 }

C.EmhMenuSpots = { {2,3}, {3,2}, {3,3}, {2,4}, {3,4} }
C.EmhRange = 2

C.EmhTreatCost    = 25
C.EmhCureCrystals = 1
C.EmhCureHours    = 12
```

### Placement invariants

Keep all of these true:

- `C.EmhStation` and `C.EmhSpot` are the same square.
- The station mesh is elevated and leaves that square's floor clear.
- `C.LegacyEmhSpot` remains `(2,4)` so old projected Doctors can be removed.
- No authored fitting occupies the station square in
  `TREK_InteriorLayout.lua` or the `.tbx` floor objects.
- `C.EmhMenuSpots` must not include the warp core, replicator, or transporter
  pad square.
- Both `C.EmhItem` and `C.EmhStationItem` remain in
  `C.ReplicatorBlocked`; they are Furniture items for world-model placement,
  not objects players should manufacture.

Any placement or generated-geometry change requires a `C.BuildRev` bump.
Moving geometry is also a migration: preserve the old coordinate long enough
for `TREK_Build.lua` to remove saved world items from existing cabins.

---

## Asset pipeline

Run:

```sh
python tools/gen_emh.py TrekShuttle/42
```

The generator is deterministic and owns all deployed EMH art:

```text
TrekShuttle/42/media/models_X/TREK_EMH.x
TrekShuttle/42/media/textures/TREK_EMH.png
TrekShuttle/42/media/models_X/TREK_EMHStation.x
TrekShuttle/42/media/textures/TREK_EMHStation.png
TrekShuttle/42/media/ui/TREK_EmhPortrait.png
TrekShuttle/42/media/sound/TREK_EmhAppear.wav

design/art/emh/preview_emh_front.png
design/art/emh/preview_emh_quarter.png
design/art/emh/preview_emh_atsize.png
design/art/emh/preview_emh_station.png
```

Never hand-edit generated meshes or textures. Change the generator or replace
the vendored source asset, regenerate, and inspect the previews.

### Doctor model

The Doctor is imported from the vendored GLB in `tools/assets/trek_emh/` and
fitted by **height**, not footprint. `C.EmhHeight` and the generator's target
height must stay in step. Trust the generator's printed bounding box rather
than the input constant.

The texture supplies the holographic treatment:

- LCARS-blue monochrome ramp;
- lifted dark values so the figure remains luminous;
- scanlines derived from mesh/world height, not horizontal texture rows.

Imported UVs are an atlas. Texture-row stripes turn into unrelated diagonals
across different mesh islands, so any level effect must be calculated from the
surface's world height.

The portrait is rendered from the same model and texture as the world figure.
Do not maintain a separate likeness by hand; that lets the panel and projected
figure drift apart.

### Projector station

The station is a custom, shallow, elevated LCARS medical/projector control. It
replaces the old `industry_01_15` fitting, which read as an air conditioner.

Its geometry must remain:

- against the east bulkhead;
- elevated above the Doctor;
- shallow enough not to read as floor furniture;
- clear beneath, because the Doctor occupies the same square;
- visibly different from a vanilla appliance or HVAC unit.

Always inspect `design/art/emh/preview_emh_station.png` after changing it and
measure the mesh if its bounds change:

```sh
python tools/meshbbox.py TrekShuttle/42/media/models_X/TREK_EMHStation.x
```

A dropped world model starts at a random yaw. Asset geometry alone does not
mount it correctly; `B.serviceEMHStation()` straightens it on initial
placement and on every later service pass.

### Replacing the Doctor source through Fal/Gemini

If generating a new source model:

1. Generate and review the candidate through the configured Fal/Gemini
   toolkit.
2. Keep the selected raw source in `tools/assets/trek_emh/`.
3. Update `SOURCE.txt` with the provider, model, date, prompt, seed or job ID,
   and selection notes.
4. Do not make normal builds depend on network access. The selected GLB must
   be vendored.
5. Regenerate with `tools/gen_emh.py`.
6. Inspect front, quarter, at-size, portrait, and in-game views.
7. Run the complete validation suite and deployer.

Judge the at-size render, not only a large preview. Facial and uniform details
that read at 600 pixels may disappear at the model's actual game size.

---

## World placement and migration

### Permanent station

`B.serviceEMHStation()` is responsible for the station. It:

1. resolves `C.EmhStation` in the interior;
2. removes the old tagged `emhPanel` tile object;
3. counts existing `C.EmhStationItem` world items;
4. removes duplicates;
5. places one station when absent;
6. straightens existing and newly placed stations;
7. logs a warning if placement fails.

The station is permanent regardless of whether the Doctor is active.

World items are saved, and generic cabin clearing deliberately preserves them
because that is also where player-dropped objects live. Therefore every
station service pass must count before placing. Blind placement creates one
new station per rebuild or timer pass.

### Summoned Doctor

`B.serviceEMH()` first services the permanent station, then removes any Doctor
saved at `C.LegacyEmhSpot`, and finally brings the current square into line
with `s.emh`.

The ship-state flag is authoritative:

```lua
s.emh = true  -- exactly one Doctor should stand at C.EmhSpot
s.emh = nil   -- no Doctor should stand there
```

The service is idempotent in both directions:

- zero Doctors while wanted → place one;
- one Doctor while wanted → straighten it;
- multiple Doctors while wanted → remove the duplicates and recover to one;
- any Doctors while dismissed → remove them all.

The service runs from summon/dismiss handling, cabin construction, and the
per-minute maintenance path. Keep the cabin-build phase: `TREK_Rebuild()`
deletes world items while ship state can still say the Doctor is active, so a
timer-only implementation leaves the state and deck disagreeing immediately
after a rebuild.

### Old cabin cleanup

Revision 23 replaces two visible pieces of the old arrangement:

- tagged tile object `emhPanel` / `industry_01_15` at `(3,3)`;
- Doctor world item at legacy spot `(2,4)`.

Do not remove the cleanup code merely because new cabins look correct. Existing
saves retain tagged objects and world items that no current layout pass visits.
Migration checks in `tests/test_multiplayer.py` deliberately plant both old
objects and require one service pass to remove them.

The BuildingEd source may keep the old tile definition in its furniture
catalogue, but the `<floor>` object list must not place `FurnitureTiles="32"`
at `(3,3)`.

---

## Runtime architecture

### Authority split

| Responsibility | Owner |
|---|---|
| Station and Doctor world items | Server / single-player authority |
| `s.emh`, cure register, reserve, and crystals | Server |
| Eligibility and refusal rules | Shared code, revalidated by server |
| Patient body changes | Server |
| Body-part synchronization | Server |
| Infection moodle and client-local body flags after cure | Patient's client, on `emhCured` |
| Panel, portrait, dialogue, local light, and sound | Each client |
| Consent prompt | Patient's client; token lifecycle remains server-owned |

A client requests an action; it never supplies an authoritative patient,
position, injury, permission, or cost.

### Protocol

Client to server:

```text
emhSummon
emhDismiss
emhLook    { who }
emhTreat   { who }
emhCure    { who }
emhAccept  { token }
emhDecline { token }
```

Server to client:

```text
emhFindings    { who, total, infected, bitten, items }
emhOffered     { token, from, what, cost }
emhTreated     { who, counts, total }
emhCureStarted { hours }
emhCured       {}
emhCureLost    {}
denied         { why, ... }
```

Remote bodies do not provide reliable medical state on a client. A panel can
read the local player's body directly, but findings for another player must
come from `emhLook` on the server.

### Shared refusal rules

The client and server both call the rules in `TREK_EMH.lua`. This keeps a
greyed control and the server's refusal aligned, but the server remains the
authority and must revalidate every request.

A valid action generally requires:

- a living player;
- permission under `Ship.canUse`;
- EMH sandbox mode enabled;
- player and patient aboard;
- player within `C.EmhRange`;
- sufficient reserve or crystals;
- a condition the requested action can address;
- valid consent when treating another player.

Never move one of these checks exclusively into the UI. A crafted command does
not pass through a greyed button.

---

## Treatment and cure

### Standard treatment

A treatment performs, in order:

```lua
Med.treatWith(patient, Med.TREATMENTS)
Med.treatWith(patient, Med.SKIN)
Med.removeForeign(patient)
Med.publish(patient)
```

The skin pass is intentionally **not** blocked by glass or bullets. The Doctor
closes the wound and removes foreign bodies afterward; that is one of the ways
he is better than the handheld dermal regenerator.

Standard treatment must leave all of these unchanged:

- bite state;
- limb zombie-infection state;
- body-level zombie infection;
- infection moodle.

Treatment costs `C.EmhTreatCost` reserve units. It must do nothing to a healthy
patient and must not spend power when there is nothing to treat.

### Zombie-infection cure

The cure is the only feature in this mod allowed to clear a bite and zombie
infection. It costs `C.EmhCureCrystals` whole crystals when treatment starts
and completes after `C.EmhCureHours` in-game hours aboard.

Leaving the cabin cancels the pending cure and does not refund the crystal.
The cure register persists through relogging; `s.emh` does not.

Per limb, `RestoreToFullHealth()` is appropriate here because the cure intends
to clear every injury field, including the bite. Do not use one-argument
`SetBitten(false)`: in build 42 it clears the bite flag and then infects and
bleeds the limb.

After restoring body parts, clear the body-level latch on the server:

```lua
damage:setInfected(false)
damage:setIsFakeInfected(false)
damage:setReduceFakeInfection(false)
damage:setInfectionTime(-1.0)
damage:setInfectionMortalityDuration(-1.0)
```

Both levels are required. `BodyDamage.isInfected` is re-derived from infected
parts and then latches; clearing only the body flag returns next tick, while
clearing only the parts leaves the latch set.

`syncBodyPart` carries body-part fields only. It does not carry the body-level
flags or infection moodle, so completion also sends `emhCured` to the patient's
client. That client clears its local body flags and
`CharacterStat.ZOMBIE_INFECTION`.

Single player cannot prove which side performed those writes because client and
server code share one process. Keep the multiplayer test that inspects the
server's own patient copy after completion.

### Consent

Self-treatment requires no prompt. Treating or curing another player requires
server-issued consent:

1. requester asks for an action on another patient;
2. server validates and issues a short-lived token;
3. only the patient's client receives the modal;
4. acceptance returns the token;
5. server consumes it once and revalidates everything;
6. only then is power or a crystal spent.

Do not spend resources when creating an offer. The requester can move, the
patient can leave, and the ship's power state can change before acceptance.

---

## User interface

`TREKEMHWindow` is an `ISPanelJoypad` using the same LCARS components as the
helm. It must remain fully usable by mouse and controller.

The panel includes:

- portrait and dialogue line;
- patient selector;
- itemized findings;
- zombie-infection status;
- reserve and crystal counts;
- Treat;
- Cure the infection;
- Full readout;
- Dismiss.

Controls are shown and greyed with a reason rather than hidden. Keep button
captions short and put full refusal text in the note/tooltip; sentence-length
refusals do not fit a 165-pixel control.

Closing the panel does not dismiss the Doctor. The explicit Dismiss action does.
One crew member closing their window must not remove the Doctor from another
crew member using the biobed.

The panel closes when its local player leaves range. The player roster is
recomputed once per frame, not separately by every widget.

`Full readout` uses a normal `ISHealthPanel` instance with
`panel.doctorLevel = C.MedDoctorLevel`. Never assign `ISHealthPanel.cheat`; it
is debug/admin gated.

---

## Menus and interaction geometry

A right-click is resolved against the floor plane, not the pixels of a tall
model. That is why the EMH uses the explicit `C.EmhMenuSpots` list rather than
only the station square.

When changing the model height or position:

1. inspect where clicks resolve in game;
2. update `C.EmhMenuSpots` only if necessary;
3. run `tests/test_layout.py`;
4. verify no EMH menu square is another fixture's own square or the transporter
   pad;
5. test both direct clicks near the station and clicks on the Doctor's upper
   body.

Do not replace the named list with a rectangular margin. The old core margin
reached the Doctor and offered to load a dilithium crystal into a hologram.

---

## Diagnostics

Use `TREK_EMH()` from the debug console while someone is aboard. The report
compares:

- whether ship state says the Doctor is active;
- number of Doctor world items at `(3,3)`;
- number of projector stations at `(3,3)`.

Healthy states are:

```text
up=false, 0 Doctors, 1 projector station
up=true,  1 Doctor,  1 projector station
```

Any other count should log a warning and be repaired by the next service pass.

Useful log searches:

```sh
sh tools/readtest.sh
grep -E "\[TREK\] (WARN|emh:)" "$USERPROFILE/Zomboid/console.txt"
```

On Windows without a Unix shell, inspect `console.txt` directly and search for
`[TREK] WARN` and `emh:`.

### Symptom map

| Symptom | Check |
|---|---|
| Old air-conditioner-like panel remains | Existing cabin has not reached revision 23, or `removeLegacyEmhPanel` did not find tag `emhPanel`; inspect build log and run `TREK_EMH()` |
| No custom station | Confirm station item/model declarations, generated mesh and texture, `B.serviceEMHStation()`, and deployed files |
| Multiple stations | Station service is placing without counting, or duplicate cleanup failed |
| Doctor appears in the middle of the room | Effective config still uses `(2,4)`, legacy item was not removed, or deployed Lua is stale |
| Station is at a random angle | `straighten()` is missing from placement or existing-item service |
| Doctor is at a random angle | Same issue in `B.serviceEMH()` |
| Ship says Doctor is up but square is empty | Build/service phase missing, placement failed, or square was unloaded |
| Doctor duplicates after rebuild/minute ticks | Placement occurs without `B.emhAt()` count |
| Menu option is absent | Click resolved outside `C.EmhMenuSpots`, client file failed to load, or deployed config is stale |
| Menu option is greyed | Read its tooltip; the UI and server use the same refusal rules |
| Treatment works locally but not for another player | Server body write or `syncBodyPart` publication is missing |
| Infection returns after cure | Limb and body-level infection were not both cleared |
| Infection moodle remains | Patient did not receive or process `emhCured` |
| Cure finishes instantly | Due-time or world-hour comparison is wrong |
| Cure never finishes | Patient left the cabin, due register was lost, or minute service is not running |
| Consent appears on requester | `emhOffered` was sent to the wrong client |
| Station files exist in source but not game | Generator ran but deployer did not; inspect deployed `models_X` and `textures` directly |

---

## Testing responsibilities

### `tests/test_assets.py`

Must verify:

- Doctor item and model declarations;
- station item and model declarations;
- both meshes and textures exist;
- portrait and summon sound exist;
- translations resolve;
- station and Doctor are blocked from replication.

### `tests/test_layout.py`

Must verify:

- no authored fitting occupies `(3,3)`;
- station and Doctor deliberately share `(3,3)`;
- the shared square is valid deck and is not the pad;
- EMH menu squares do not collide with another fixture's square;
- `.tbx` and runtime container geometry remain consistent.

The `.tbx` comparison is strongest for containers. Directly inspect its floor
object list when removing a non-container fitting such as the old EMH panel.

### `tests/test_helm.py`

Must render at least:

- a healthy patient;
- a badly injured and infected patient;
- long names and refusal text;
- disabled Treat and Cure for distinct reasons;
- every control reachable by controller;
- focus returned correctly on close.

### `tests/test_multiplayer.py`

The EMH scenarios must cover:

- one permanent station in a fresh cabin;
- station yaw is zero;
- station and Doctor coordinates are identical;
- no Doctor at `C.LegacyEmhSpot`;
- old tagged appliance panel removed;
- legacy Doctor removed;
- repeated service leaves one station and at most one Doctor;
- rebuild restores the station and an active Doctor;
- summon and dismiss through the real menu/panel path;
- treatment leaves bite and zombie infection untouched;
- cure spends a crystal immediately and lands only after the configured time;
- every limb- and body-level infection field clears;
- infection remains cleared after body updates;
- client moodle clears;
- leaving the cabin cancels without refund;
- sandbox and power refusals;
- two-client visibility;
- consent appears only on the patient;
- server owns all body and world changes;
- patient receives all body-part syncs;
- forged and expired requests are refused;
- owner-and-crew access is enforced.

A test that calls a server handler directly does not prove a player can reach
the feature. Keep the context-menu and panel-driven path.

---

## Safe change procedures

### Change the station appearance

1. Edit the station-generation section of `tools/gen_emh.py`.
2. Regenerate all EMH assets.
3. Inspect `preview_emh_station.png`.
4. Measure the station mesh.
5. Confirm the geometry stays elevated and clear beneath.
6. Run assets, layout, multiplayer, and full Lua checks.
7. Deploy and directly confirm both station files in the installed mod.
8. Fully restart the game and beam aboard.

### Change the Doctor model or likeness

1. Select and vendor the new GLB; update `SOURCE.txt`.
2. Keep the generator deterministic and offline after selection.
3. Regenerate.
4. Inspect front, quarter, at-size, and portrait renders.
5. Check facing, scale, scanline orientation, silhouette, and likeness in game.
6. Run all checks and deploy.

### Move the station and Doctor

1. Pick one shared destination square.
2. Set both `C.EmhStation` and `C.EmhSpot` to it.
3. Preserve the previous square as a legacy coordinate.
4. Update `B.serviceEMH()` migration cleanup if necessary.
5. Remove any authored fitting from the destination in both `.tbx` and runtime
   layout.
6. Reassess `C.EmhMenuSpots` and cross-fixture collisions.
7. Bump `C.BuildRev`.
8. Add a migration test that plants old station/Doctor objects.
9. Run the complete suite and test an existing save as well as a fresh world.

### Change treatment scope

1. Decide whether the change belongs to `Med.TREATMENTS`, `Med.SKIN`,
   `Med.CURE`, or EMH-only ordering.
2. Preserve the rule that standard treatment never changes `Med.CURE` fields.
3. Set every field under test before asserting it survives or clears.
4. Tick `BodyDamage` after a cure to test the infection latch.
5. Run single-player and multiplayer scenarios; either alone is insufficient.

### Change costs or timing

Update the constants only, then check:

- panel values and refusal text;
- server validation;
- resource spending order;
- no spending on offers or refused actions;
- cure persistence across relog;
- abandonment behavior;
- tests using the constants still include a fixed lower/upper sanity bound
  where appropriate.

---

## Engine facts not to re-derive

- `BodyPart.SetBitten(false)` with one argument infects and bleeds the limb.
- `RestoreToFullHealth()` writes the whole body-part state directly and is
  appropriate only for the full EMH cure in this mod.
- `infectionTime < 0` means the infection countdown has not started; reset it
  to `-1.0`, not `0`.
- `BodyDamage.isInfected` is a one-way latch derived from infected parts. Clear
  both levels in one pass.
- The infection moodle's writer stops running after cure, so the patient's
  client must explicitly reset it.
- `syncBodyPart` works only on the server and carries body-part fields, not
  body-level flags or stats.
- `setHaveBullet(false)` is the wrong overload; use
  `setHaveBullet(false, 0)`.
- A world inventory object's constructor chooses a random yaw when none is
  set. Straighten fixtures after placement and during maintenance.
- Generic square clearing preserves world items and tagged mod objects. Every
  migration must explicitly name obsolete ones.
- A right-click resolves to a floor square, not to the visible pixels of a tall
  model.
- A client may request treatment or placement but may not authoritatively
  change a body, ship state, or cabin world object.
- A vanilla Lua call site proves reachability, not that the method has the
  semantics this feature needs. Read bytecode when behavior matters.

---

## In-game acceptance checklist

After deployment and a full restart:

1. Beam aboard so revision 23 is applied.
2. Confirm the old appliance-looking wall object is gone.
3. Confirm one custom LCARS projector station is mounted at the sick-bay wall.
4. Right-click the station and consult the EMH.
5. Confirm exactly one Doctor appears directly below the station, not at the
   old middle-of-room square.
6. Look from both sides for facing, scale, clipping, and station clearance.
7. Confirm the portrait resembles the projected model.
8. Treat ordinary injuries and verify bite/infection remain.
9. Start a cure and verify one crystal is spent immediately.
10. Complete the cure aboard and verify bite, infection, and moodle all clear.
11. Start another cure, leave the cabin, and verify cancellation without a
    refund.
12. Dismiss and resummon the Doctor; the permanent station must remain.
13. With a controller, navigate every control, activate with A, close with B,
    and verify focus returns to the game.
14. Run `TREK_EMH()` and confirm one station plus zero or one Doctor matching
    ship state.
15. Repeat the placement check in an existing revision-22 save to exercise the
    old panel and old Doctor cleanup.

Static validation proves the mod's own logic and generated references. Only
this in-game pass proves final rendering, click geometry, engine placement, and
visual likeness.
