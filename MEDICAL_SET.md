# The medical set — implementation guide

Three items: **medical tricorder**, **hypospray**, **tricorder**. Roadmap item 3.

`DEV_GUIDE.md` first, then `MULTIPLAYER.md` for the client/server split.
`PHOTON_TORPEDOS.md` is the worked example of a feature built to these rules.

Everything below was verified with `tools/pzapi.py` and a grep of vanilla Lua
before it was written down. **Nothing here has been built.**

---

## 1. The one that will bite you

`ISHealthPanel.cheat` is the obvious way to build the medical tricorder. It
bypasses every Doctor-skill gate in the panel, which is exactly the feature.

**Do not use it.**

```lua
ISHealthPanel.cheat = false or getDebug()     -- ISHealthPanel.lua:5
```

It is **on under `-debug` and off otherwise**, and the only other things that
set it are `ISAdminPowerUI` and `getPlayer():isHealthCheat()`. So it works on
this developer's machine, works for an admin, and does nothing for every
Workshop subscriber — the `setGodMod` failure shape from `DEV_GUIDE.md`,
*The jar is not the API*, one more time.

**Use `doctorLevel` instead.** It is assigned exactly once, in
`ISHealthPanel:new` (line 973), and every gate reads it:

```lua
if healthPanel.doctorLevel > 2  ... -- evaluate a wound
if healthPanel.doctorLevel > 4  ... -- pain, burns, deep wounds
if healthPanel.doctorLevel > 6  ... -- stitches
if healthPanel.doctorLevel > 8  ... -- wound infection
```

Build the panel, set `panel.doctorLevel = 10`, done. Per-instance, no global
state, no debug gate, and it is the number the code already consults.

---

## 2. Verified engine facts

| Fact | Where |
|---|---|
| `ISHealthPanel.cheat` is `false or getDebug()`; otherwise admin-only | `ISHealthPanel.lua:5`, `ISAdminPowerUI.lua:135,461` |
| `doctorLevel` is set once at construction and only ever read after | `ISHealthPanel.lua:973` |
| Doctor gates are `> 2` wound, `> 4` pain/burn/deep, `> 6` stitch, `> 8` infection | `ISHealthPanel.lua:633-830` |
| `ISHealthPanel:new(player, x, y, w, h)` then `:wrapInCollapsableWindow(title, false)` | `ISMedicalCheckAction.lua:49-59` |
| Seeing **another player's** damage in MP needs `startReceivingBodyDamageUpdates(other)` / `stopReceiving…` | `ISMedicalCheckAction.lua:73`, `ISHealthPanel.lua:381` |
| `BodyPart` is `zombie.characters.BodyDamage.BodyPart`; all treatment setters are public | `pzapi.py` |
| Zombie infection is `BodyDamage.setInfected(boolean)`; a **wound** infection is `BodyPart.setInfectedWound(boolean)` — different things | `pzapi.py` |
| A bite is `BodyPart.SetBitten(boolean)` (capital S) | `pzapi.py` |
| `IsoDoor` / `IsoThumpable`: `setLocked`, `setIsLocked`, `setLockedByKey`, `isLockedByPadlock` | `pzapi.py` |
| **Every vanilla Lua call site for those lock setters is `DebugContextMenu` or the tutorial** — no ordinary gameplay caller exists | grep |
| `cell:getZombieList()` works and this mod already uses it | `TREK_Core.lua:383` |

### The treatment setters

```
setBleeding(false) / setBleedingTime(0)      bleeding
setDeepWounded(false) / setDeepWoundTime(0)  deep wounds
setInfectedWound(false)                      ordinary wound infection
setBurnTime(0) / setNeedBurnWash(false)      burns
setFractureTime(0) / setSplint(true, f)      fractures
setStitched(true) / setStitchTime(0)         stitches
setBandaged(true, life)                      dressings
SetHealth(f)                                 the part's health
SetBitten(false)                             *** a bite -- see below ***
```

---

## 3. Hypospray

**Decided: it does not cure a bite.** So it must never call `SetBitten(false)`
or `BodyDamage.setInfected(false)`. Those two are the EMH's, later, and they
are the whole reason the EMH is worth building.

It treats everything else, in one use, on one body part or all of them:
bleeding, deep wounds, wound infection, burns, fractures, pain, part health.

The distinction to keep straight, because the names are nearly the same:

- `BodyPart.setInfectedWound(false)` — an ordinary infected cut. **Cure it.**
- `BodyDamage.setInfected(false)` — the zombie virus. **Leave it.**

**Where it runs.** A client may heal **its own character** — same rule and same
reason as "a client moves only its own character" (`MULTIPLAYER.md`): body
damage belongs to the owning client and syncs from there. Treating *someone
else* is a server command, and is the EMH's problem, not this item's.

Start it as self-use only. That keeps the whole item client-side and needs no
new protocol.

---

## 4. Medical tricorder

Full diagnosis regardless of Doctor skill — section 1 is the mechanism.

```lua
local panel = ISHealthPanel:new(patient, x, y, 400, 400)
panel:initialise()
panel.doctorLevel = 10          -- NOT ISHealthPanel.cheat
panel:wrapInCollapsableWindow(title, false):addToUIManager()
```

Two things to settle in game:

1. **Self versus other.** On yourself it is pure UI and entirely client-side.
   On another player in MP it additionally needs
   `startReceivingBodyDamageUpdates(other)` and a matching `stopReceiving…`
   when the panel closes, or the readout is a snapshot that never updates.
2. **The controller.** Every panel in this mod must work with a gamepad
   (`DEV_GUIDE.md`). `ISHealthPanel` is not an `ISPanelJoypad`, so check what
   it does on a pad **before** designing around it — this may need a wrapper
   or a purpose-built LCARS panel rather than vanilla's.

---

## 5. Tricorder

Two features, and they are not equally risky.

### Unlocking

`setLocked(false)` / `setLockedByKey(false)` / `setIsLocked(false)` all exist
and are public — **and every call site in vanilla Lua is the debug menu or the
tutorial.** That is not proof they are gated, but it is exactly the pattern
that preceded two of this project's worst afternoons, so:

- verify it works for an ordinary character before building anything on it;
- **a lock is world state, so the change belongs on the server.** A client
  asks, `TREK_Server.lua` validates and applies. A client calling these
  directly is the "no client edits the world" rule broken, and
  `tests/pz_sim.lua` counts client world edits for exactly that reason.
- `isLockedByPadlock()` is a separate case. Decide whether it is covered.

### Sensor sweep

`cell:getZombieList()` is proven — `TREK_Core.lua:383` already sweeps it for
the shields, so copy that, including its guards.

**It must be sliced.** A sweep is the landing search all over again: see
*Slice any search that touches thousands of squares*. Keep a cursor, do a
fixed number per tick, and do not allocate inside the loop.

Decide what it reports: zombies only, or items and doors too. Zombies alone is
one list and already available; items means walking squares, which is the
expensive version and needs the slicing to be right.

---

## 6. Rules this inherits

- **Verify every new engine call**: `pzapi.py` for exists-and-public, a grep of
  vanilla Lua for "may I call it", `javadis.py` for under-what-condition.
- **No `-debug`-gated or admin-only calls.** Section 1 is one; assume there are
  more in this area, because medical and admin overlap heavily.
- **The server owns the world.** UI and a character's own body are the client's;
  locks are not.
- **Every panel works with a controller.**
- **Read the result back and log it.** A treatment that silently does nothing
  looks exactly like one that worked.
- **Icons**: 32×32 if the item has an `AttachmentType`, 64×64 otherwise.
  `tests/test_assets.py` enforces it.
- **Bump `C.BuildRev`** if anything goes into the cabin's loot, and remember
  new loot reaches **new worlds only**.

---

## 7. Suggested order

1. **Hypospray.** Smallest, design already decided, entirely client-side for
   self-use, and it establishes the body-part plumbing the other two and the
   EMH all build on.
2. **Medical tricorder.** One panel, one field. Settle the controller question
   here because the EMH will inherit whatever is decided.
3. **Tricorder.** Sweep first (proven API, known slicing pattern), unlocking
   second — verify the lock setters work for an ordinary player *before*
   designing the interaction around them.

Nothing here has been fired with two people connected, and neither has
anything else added since the torpedoes. The two-player session in
`ROADMAP.md` grows with every one of these.
