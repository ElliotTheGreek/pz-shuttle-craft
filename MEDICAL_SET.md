# The medical set — how it works

Three items: **hypospray**, **medical tricorder**, **tricorder**. Roadmap item 3.

**Built 2026-09-20. Not yet seen in game.** Everything below is either an
engine fact verified with `tools/pzapi.py`, `tools/javadis.py` and a grep of
vanilla Lua, or a decision taken while building it. The parts that only the
game can settle are listed at the bottom.

`DEV_GUIDE.md` first, then `MULTIPLAYER.md` for the client/server split.
`PHOTON_TORPEDOS.md` is the other worked example of a feature built to these
rules.

```
media/lua/shared/TREK/TREK_Medical.lua   treatment, doses, what counts as a lock
media/lua/client/TREK/TREK_MedKit.lua    menus, the panels, the sweep, refills
media/lua/server/TREK/TREK_Server.lua    the `unlock` command handler
media/scripts/trekshuttle.txt            the three items and two sounds
tools/gen_medical.py                     the two sounds (the icons are Gemini's)
design/art/medical/                      the icon originals and their contact sheet
```

---

## 1. The four that would have bitten

### `ISHealthPanel.cheat` is a debug flag

It is the obvious way to build the medical tricorder, and it works for this
developer and for nobody on the Workshop:

```lua
ISHealthPanel.cheat = false or getDebug()     -- ISHealthPanel.lua:5
```

The only other things that set it are `ISAdminPowerUI` and
`getPlayer():isHealthCheat()`. It is the `setGodMod` failure shape from
`DEV_GUIDE.md`, *The jar is not the API*.

**`doctorLevel` is the real lever.** It is assigned exactly once, in
`ISHealthPanel:new` (line 973), and every gate reads it:

```lua
if healthPanel.doctorLevel > 2  ... -- evaluate a wound
if healthPanel.doctorLevel > 4  ... -- pain, burns, deep wounds
if healthPanel.doctorLevel > 6  ... -- stitches
if healthPanel.doctorLevel > 8  ... -- wound infection
```

Build the panel, set `panel.doctorLevel = C.MedDoctorLevel`, done. Per
instance, no global state, no debug gate, and it is the number the code
already consults. `tests/test_multiplayer.py` fails if anything sets the
global instead.

### `BodyPart.RestoreToFullHealth()` cures a bite

**This is the one that was nearly shipped.** It is the tidy way to mend a
limb, and its bytecode does considerably more than mend it:

```
  1  ldc_w  100.0     putfield BodyPart.health
 37  fconst_0         putfield BodyPart.biteTime
 42  iconst_0         putfield BodyPart.bitten        <-- here
 92  iconst_0         putfield BodyPart.infectedWound
```

So the convenient call silently hands the hypospray the one cure the design
says it must not have, the EMH loses its reason to exist, and **nothing in the
game would report it** — the item would simply be better than intended.

`TREK_Medical.lua` therefore sets the fields it means to set, one at a time,
and never calls that method. The check that holds it there is
`tests/test_multiplayer.py`'s `medical()`: a body is bitten and infected
before a dose, and both are asserted to have survived it.

A convenience method is a bundle of writes somebody else chose. Read the
bundle.

### A lock setter's own sync is one-sided

`setLockedByKey(b)` calls `setLockedByKey(b, true)`, which does fire the
engine's own sync — **only when it is not the server**:

```
 21  invokevirtual  IsoDoor.setIsLocked(Z)
 24  getstatic      GameServer.server
 27  ifne           -> 55            <-- on a server, skip the whole thing
 43  invokevirtual  IsoDoor.sync(3)  <-- locked
 51  invokevirtual  IsoDoor.sync(4)  <-- unlocked
```

A lock is world state, so the server is what opens it — and the server is
exactly the process in which that branch does nothing. A door opened by the
authority would stay shut on every client's screen.

`obj:sync()` is the explicit call that covers both: on a server it writes a
`SyncIsoObject` packet to every connection, on a client it sends one to the
server, and in single player there is nobody to tell. It is public, and
vanilla Lua calls it in a dozen places including `server/ClientCommands.lua`.

### The two infections have nearly the same name

- `BodyPart.setInfectedWound(false)` — an ordinary infected cut. **Cured.**
- `BodyDamage.setInfected(false)` — the zombie virus. **Never touched.**

`BodyPart.setWoundInfectionLevel(-1)` clears the level, and `-1` rather than
`0` is what vanilla's own health panel writes; 0 is a wound that is merely not
infected *yet*.

---

## 2. Verified engine facts

| Fact | Where |
|---|---|
| `ISHealthPanel.cheat` is `false or getDebug()`; otherwise admin-only | `ISHealthPanel.lua:5`, `ISAdminPowerUI.lua:135,461` |
| `doctorLevel` is set once at construction and only ever read after | `ISHealthPanel.lua:973` |
| Doctor gates are `> 2` wound, `> 4` pain/burn/deep, `> 6` stitch, `> 8` infection | `ISHealthPanel.lua:633-830` |
| **`ISHealthPanel` IS an `ISPanelJoypad`** — stick navigation, A to act, B to close, all built in | `ISHealthPanel.lua:4,902-959` |
| `ISHealthPanel:new(patient, x, y, w, h)`, then `doctorLevel`, then `wrapInCollapsableWindow(title, false):addToUIManager()` | `ISMedicalCheckAction.lua:48-59` |
| `wrapInCollapsableWindow` sets `window.nested` to the panel | `ISUIElement.lua:1771` |
| Examining **another player** in MP goes through consent: `requestMedicalCheck(target, requester)` raises a yes/no, and only a yes reaches `ISMedicalCheckAction` | `ISHealthPanel.lua:1942-1962` |
| `startReceivingBodyDamageUpdates` / `stopReceiving…` are handled by `ISMedicalCheckAction` and `ISHealthPanel:update()` themselves | `ISMedicalCheckAction.lua:73`, `ISHealthPanel.lua:381,416` |
| `BodyPart.RestoreToFullHealth()` clears `bitten`, `biteTime` and `infectedWound` | `javadis.py` |
| Zombie infection is `BodyDamage.setInfected(boolean)`; a **wound** infection is `BodyPart.setInfectedWound(boolean)` | `pzapi.py` |
| A bite is `BodyPart.SetBitten(boolean)` (capital S) | `pzapi.py` |
| Full part health is **100.0** — the constant `RestoreToFullHealth` writes | `javadis.py` |
| `BodyPart.setBandaged` has **no vanilla Lua call site**; vanilla bandages through `BodyDamage:SetBandaged(index, on, life, alcoholic, type)` | grep |
| `IsoDoor` / `IsoThumpable` / `IsoWindow`: `setLocked`, `setIsLocked`, `setLockedByKey`, `isLockedByPadlock` | `pzapi.py` |
| **Every vanilla Lua call site for those lock setters is `DebugContextMenu`, `AdminContextMenu` or the tutorial** | grep |
| `IsoObject.sync()` is public, and vanilla Lua calls it on both sides | `ClientCommands.lua:780`, `ISFluidContainer.lua:102` |
| `SafeHouse.isSafeHouse(square, username, true)` returns the safehouse only when the named player is **not** a member of it | `javadis.py`, `ISBuildUtil.lua:12,15` |
| `cell:getZombieList()` works and this mod already uses it | `TREK_Core.lua:383` |
| `OnFillInventoryObjectContextMenu(playerNum, context, items)` — vanilla's own comment calls it the way to add options "without mod conflicts" | `ISInventoryPaneContextMenu.lua:935` |
| An entry in `items` is either an `InventoryItem` or a stack — a table with an `items` list | `ISRemoveItemTool.lua:348-358` |
| `character:playSoundLocal(name)` is public, with fifteen vanilla call sites | `ISMap.lua:210` and others |

### The treatment setters

```
setBleeding(false) / setBleedingTime(0)          bleeding
setDeepWounded(false) / setDeepWoundTime(0)      deep wounds
setInfectedWound(false) / setWoundInfectionLevel(-1)   an ordinary infected cut
setBurnTime(0) / setNeedBurnWash(false)          burns
setFractureTime(0) / setSplint(false, 0)         fractures, and the splint with them
setAdditionalPain(0)                             pain
setStiffness(0)                                  stiffness
SetHealth(100)                                   the part's health
SetBitten(false)                                 *** never called here ***
```

`Med.TREATMENTS` in `TREK_Medical.lua` is that list as data, in that order,
and it is deliberately the only place it exists: adding a bite to that table
is the single change that would break the promise, so it is worth having one
place to look.

---

## 3. Hypospray

**One dose treats everything above at once, on every body part.** It does not
cure a bite and it does not clear the zombie infection.

- **Six doses** (`C.HyposprayDoses`), kept in the item's own mod data — not in
  its condition or an ammo count, both of which are engine state with engine
  opinions about them.
- **The ship replicates more, and only the ship.** One dose per
  `C.HyposprayRechargeTicks` (900 ticks, so fifteen seconds) while the carrier
  is aboard, and none at all in the field. Tied to the cabin rather than to a
  timer on the item, because a hypospray that refilled itself wherever you
  left it makes the dose limit a delay rather than a decision, and the
  decision — push on with two doses, or go home — is the only interesting
  thing about the number.
- **A dose is never wasted.** It is spent only when there was something to
  treat *and* the treatment took. Both halves are real guards and it takes
  removing both to waste one; the mutation check proves that.
- **Everything is read back.** `Med.treat` asks whether a condition is present,
  applies the fix, and asks again; only a condition that was there and then
  was not is counted. That is what the halo note lists, so "Hypospray:
  bleeding stopped, burns treated" is a report rather than a hope.

**Where it runs:** entirely on the client, for its own character. Body damage
belongs to the owning client and syncs from there, the same rule and the same
reason as "a client moves only its own character". Treating *somebody else* is
the EMH's problem.

---

## 4. Medical tricorder

Vanilla's own `ISHealthPanel` with `doctorLevel` set to `C.MedDoctorLevel`.

**On yourself** it is pure UI and entirely client-side: right-click the item →
*Scan yourself*.

**On somebody else** — right-click them in the world → *Scan <name>* — it goes
through the engine's own consent flow, `requestMedicalCheck`, which raises a
yes/no on their screen. Only a yes reaches `ISMedicalCheckAction`, and
`TREK_MedKit.upgradeMedicalCheck` wraps that action to raise `doctorLevel` on
the panel it opens, when the doctor is carrying a medical tricorder.

A wrapper rather than a reimplementation because that action also does the
animation, the proximity checks, the body-damage subscription, the window
bookkeeping and the joypad focus — all of which we would otherwise be copying
and then failing to keep up to date. The reading of who is carrying what is
taken **before** calling through, which is the lesson the radial menu cost
(`DEV_GUIDE.md`, *A hook on a toggle must ask before it calls through*).

**The controller question is answered, and `MEDICAL_SET.md` had it backwards.**
This file used to say "ISHealthPanel is not an ISPanelJoypad, so check what it
does on a pad before designing around it". It is one —
`ISHealthPanel = ISPanelJoypad:derive("ISHealthPanel")` — with stick
navigation, A to act and B to close already in it, and vanilla's own medical
check hands it the joypad focus. We do the same and nothing else was needed.

**Open design question for the author.** The panel shows everything a Doctor
10 would see, which is wounds, pain, burns, stitches and *wound* infection. It
does **not** reveal the zombie infection, because `MEDICAL_SET.md` scoped it
to the Doctor gates and the EMH is meant to be the thing that knows. A
tricorder that announced "you are infected" with no cure in reach would be a
different and much harsher item. Worth deciding before the EMH is built.

---

## 5. Tricorder

### Sensor sweep

Right-click the item → *Sensor sweep* opens an LCARS contact plot: you at the
centre, north up, a blip per contact, and counts in three range bands.

- Reads `cell:getZombieList()`, which the shields already walk every tick, so
  the call is proven in this mod and in game.
- **Sliced**, with a cursor and `C.SweepPerTick` (96) contacts a tick, for the
  same reason the landing search is sliced: a pass over a horde in one frame
  is not slow, it is a hard lock. The test puts 400 contacts in front of it
  and fails if one slice finishes them.
- Reports what **this client is simulating** within `C.SweepRadius` (40
  tiles). On a server that is not quite every zombie there is, which is honest
  — it is a sensor reading, not omniscience.
- The panel is an `ISPanelJoypad` built from the helm's own LCARS parts, so it
  looks like the same ship and works on a pad. `tests/test_helm.py` drives it.

The plot is drawn, never placed: nothing about it touches a world object, the
same rule the torpedo's flight follows.

### Lock override

Right-click a locked door, window or gate → *Override the lock*.

**It is a server command**, because a lock is world state. The client looks
first only so it can offer the option and explain a refusal in the menu rather
than in silence; the server looks again from scratch, because a client is a
request and never a fact. Then `Med.unlock` clears the flags and calls
`obj:sync()` — see section 1 for why that call is not optional.

The server checks, in order: the player is alive, the numbers are sane, the
cooldown has expired, **the tricorder is really in that player's inventory on
the server's own copy**, the lock is within `C.UnlockRange` of where the
server thinks they are, and the chunk is loaded.

**What it will not open, and this is a decision rather than a limitation:**

- **a padlock.** Somebody fitted that by hand. The option is still shown and
  greyed with a reason, because an option that silently is not there teaches a
  player that the mod is broken;
- **anything inside a safehouse they are not a member of.**

Both are another player's property, and a mod that picks them is a griefing
tool on every server that installs it — with no setting to turn it off,
because a server owner would first have to know it was there.

`C.UnlockCooldownMs` (20 s) is spent only on an attempt that reached a real
lock. Clicking a padlock does not lock you out of the tool for twenty seconds.

---

## 6. Where it is in the ship

Both sick-bay lockers stock `C.Loot.medical`, and the forward one at 5,1
carries one of each instrument outright — `special = "medkit"`, the same
mechanism that puts four phasers in the locker at 5,6. Leaving them to the
loot list is not enough: the fill walks that list from a rolling cursor, so
three entries among thirty-one can miss both lockers and the ship sails with
no tricorder aboard.

`tests/test_layout.py` cross-checks every `special` in the layout against the
rules in `TREK_Build.lua`, both ways, so a typo fails a test instead of
quietly stocking nothing.

**Revision 14, so new worlds only** (`DEV_GUIDE.md`, *Never restock an
existing container*). An existing save will not grow a tricorder.

---

## 7. Still to settle, in game

Nothing here has been seen in the game yet. In the order worth checking:

1. **The three items exist and are in the sick bay.** Fresh world, beam up,
   open the forward starboard locker.
2. **The hypospray.** Take some damage, use it, read the halo note. Then check
   the thing that matters: a bite must still be a bite afterwards, and the
   infection moodle must still be there.
3. **The medical tricorder on yourself**, with a controller as well as a
   mouse — the panel is vanilla's and should already work on a pad.
4. **The sensor sweep**, standing somewhere with zombies in view: do the blips
   agree with what is actually around you, and does the framerate survive a
   horde.
5. **The lock override** on an ordinary locked house door, and then on a
   padlocked one, which must refuse and say why.
6. **Two players**: the override from a client, seen by the other machine; a
   medical scan requested and accepted; and the refusal for a player carrying
   no tricorder.

The two-player session in `ROADMAP.md` grows by items 6.
