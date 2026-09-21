# The medical set

How the shuttle's four medical instruments work, how to change them, and what
will bite you if you do.

**Built 2026-09-20. Not yet seen in game** — section *Still to settle, in game*
is the list to work through the first time it is carried in.

| | |
|---|---|
| **Hypospray** | injected: an infected cut, pain, stiffness, fractures, and the open wounds too. Six doses, refilled aboard. |
| **Dermal regenerator** | skin: lacerations, scratches, deep wounds, bleeding, burns, and the stitches and dressing over them. Free. |
| **Medical tricorder** | vanilla's health panel with every Doctor gate open, on you or — with their consent — on somebody else. |
| **Tricorder** | a sliced sensor sweep drawn as a contact plot, and a lock override that asks the server. |

`DEV_GUIDE.md` is the general one and its *Rules that exist because they were
broken* still apply here. `MULTIPLAYER.md` is the client/server split.
`PHOTON_TORPEDOS.md` is the other worked example. This file is the medical set.

---

## What happens when the player uses one

Build 42 has **no script hook for "using" an arbitrary item** — the two routes
that exist are a food item's eat action and a literature item's read action,
and both consume or replace the thing. A tricorder is used and kept. So every
one of these is an `OnFillInventoryObjectContextMenu` option, which is the
event vanilla's own comment calls the way to add options "without mod
conflicts".

```
hypospray / dermal regenerator      (client only, start to finish)

  right-click in inventory -> M.fillInventoryMenu
      "Administer hypospray (6 left)"   greyed at 0, never hidden
      "Run the dermal regenerator"
  -> M.useHypospray / M.useDermalRegen
       Med.needsTreatment(...)          nothing to treat -> say so, spend nothing
       Med.treat / Med.regenerate       -> Med.treatWith(character, list, skip)
           per part, per entry:  ask -> fix -> ask again
                                 counted only if it really changed
       Med.setDoses(item, left - 1)     hypospray only
       playSoundLocal, halo note naming what changed

medical tricorder, on yourself      (client only)

  right-click -> "Scan yourself" -> M.scanSelf -> M.openHealthPanel
      ISHealthPanel:new(patient, ...)  :initialise()
      panel.doctorLevel = C.MedDoctorLevel     <- the whole feature
      :wrapInCollapsableWindow(title, false):addToUIManager()
      JoypadState focus handed over, as vanilla's medical check does

medical tricorder, on somebody else (consent, then a wrapper)

  right-click them -> "Scan <name>" -> M.scanOther
      requestMedicalCheck(target, requester)   engine raises a yes/no on THEIR screen
  ... only on yes ...
      engine -> ISMedicalCheckAction:perform
      M.upgradeMedicalCheck wraps it: reads who is carrying what FIRST,
      calls through, then raises doctorLevel on window.nested

tricorder, sensor sweep             (client only)

  right-click -> "Sensor sweep" -> M.openSweep
      TREKTricorderWindow (ISPanelJoypad, helm LCARS parts)
      M.startSweep: snapshot cell:getZombieList(), position, cursor = 0
  OnTick -> M.serviceSweep: C.SweepPerTick contacts a tick, banded by range
      done -> M.lastSweep -> window:onSweepDone -> the plot draws

tricorder, lock override            (client asks, SERVER opens)

  right-click a locked door -> M.fillWorldMenu
      Med.lockOn(sq, username)   offered; a padlock is shown GREYED with a reason
  -> M.onOverride -> Core.send("unlock", {x, y, z})

  server  Net.onServer("unlock")
          alive / sane numbers / cooldown / tricorder really in THEIR inventory
          / within C.UnlockRange of where the SERVER thinks they are / chunk loaded
          Med.lockOn(sq, name)   asked again, from scratch
          Med.unlock(obj)        clears the flags AND calls obj:sync()
          Net.toClient("unlocked", {ok, why})

  client  Net.onClient("unlocked") -> note, or the reason it was refused
```

Three orderings in there are deliberate and easy to break:

- **A dose is spent after the treatment took, not before.** Two guards, and it
  takes removing both to waste one.
- **The wrapper reads before it calls through.** By the time
  `ISMedicalCheckAction:perform` returns, the health-window table has been
  rewritten. Same lesson as the radial menu (`DEV_GUIDE.md`, *A hook on a
  toggle must ask before it calls through*).
- **The cooldown is spent on an attempt that reached a real lock**, not on a
  refusal. Clicking a padlock does not lock the tool for twenty seconds.

---

## Where everything lives

| File | What it holds |
|---|---|
| `shared/TREK/TREK_Config.lua` | every constant — section *The medical set* |
| `shared/TREK/TREK_Medical.lua` | `Med.TREATMENTS`, `Med.SKIN`, `Med.treatWith`, doses, `Med.lockOn` / `Med.unlock`. No side effects; loads everywhere |
| `client/TREK/TREK_MedKit.lua` | the menus, both panels, the sweep job, dose refills, the `ISMedicalCheckAction` wrapper |
| `server/TREK/TREK_Server.lua` | the `unlock` handler — the only place a lock is opened |
| `server/TREK/TREK_Build.lua` | `SPECIALS.medkit` — what the sick-bay locker is guaranteed |
| `shared/TREK/TREK_InteriorLayout.lua` | `special = "medkit"` on the locker at 5,1 |
| `media/scripts/trekshuttle.txt` | the four `item` blocks and three `sound` blocks |
| `lua/shared/Translate/EN/` | `ItemName`, `Tooltip`, and every `IGUI_TREK_` string |
| `tools/gen_medical.py` | the three sounds. **The icons are not made here** — they come from the Gemini toolkit |
| `design/art/medical/` | icon originals, the contact sheet, and what was sent to `analyze-image` |
| `tests/test_multiplayer.py` | `medical()` and `medical_multiplayer()` |
| `tests/test_helm.py` | the tricorder's contact plot, drawn and driven |
| `tests/pz_sim.lua` | bodies, locks, safehouses, `ISHealthPanel`, context menus |

---

## Changing it

### What an instrument treats

Both treatment lists are **data, in one place**, and that is the point:

```lua
Med.TREATMENTS   -- the hypospray
Med.SKIN         -- the dermal regenerator
```

Each entry is `{ key, ask(part, bodyDamage), fix(part, bodyDamage) }`. `ask`
returns truthy while the condition is present, so the same function is the
before reading *and* the after check — `Med.treatWith` runs ask → fix → ask,
and counts nothing that did not actually change.

To add a condition, add an entry and a `*_TEXT` string in `TREK_MedKit.lua` so
the halo note can name it. To move one between instruments, move the entry.

**Adding a bite or the zombie infection to either list is the single change
that breaks the whole design**, which is exactly why they are tables you can
read at a glance rather than a block of ifs. `medical()` bites a body and
infects it before every dose and every regenerator pass and asserts both
survived.

### The split between the two

The overlap on deep wounds, bleeding and burns is deliberate — the hypospray
stays the all-in-one emergency dose. What keeps a free, unlimited regenerator
from making it pointless is **scope, not cost**:

| | Hypospray | Dermal regenerator |
|---|---|---|
| lacerations, scratches | — | **yes** |
| stitches, dressings | — | **yes** |
| deep wounds, bleeding, burns | yes | yes |
| part health | yes | yes |
| **infected cut** | **yes** | — |
| **pain, stiffness** | **yes** | — |
| **fractures** | **yes** | — |
| bites, zombie infection | never | never |
| cost | 6 doses, refilled aboard | free |

An infected wound is still what kills you, and it is still the hypospray that
deals with one. If you widen `Med.SKIN` into that column, the hypospray has
nothing left to be.

### Doses

`C.HyposprayDoses` (6) and `C.HyposprayRechargeTicks` (900 ticks, so fifteen
seconds a dose **while aboard**). Kept in the item's own mod data — not its
condition, not an ammo count, both of which are engine state with engine
opinions about them; mod data on an `InventoryItem` saves with the item and
travels with it between containers, players and worlds.

An item that has never been used has no entry at all, so **absent means full**.
Reading it as empty would ship every locker stocked with dead injectors.

The refill is tied to the cabin rather than to a timer, and that is the whole
design: a hypospray that refilled itself wherever you left it makes the limit a
delay rather than a decision, and the decision — push on with two doses, or go
home — is the only interesting thing about the number.

### The regenerator's two refusals

Both live in `Med.obstructed` and the `bandage` entry's `ask`:

- **glass or a bullet still in the part** — the site is skipped, the rest of
  the body is still treated, and `counts.skipped` drives a second note naming
  what is in the way. Skin does not close over a shard, and a mod that sealed
  one inside while reporting success is the failure shape this project keeps
  cataloguing. Tweezers keep a reason to exist.
- **a dressing on a bitten limb** — it cannot cure the bite, so taking the
  bandage off one is worse than doing nothing.

Removing either is a one-line change and both are mutation-checked.

### The health panel

`panel.doctorLevel = C.MedDoctorLevel` on the instance. **Never
`ISHealthPanel.cheat`** — see *What would have bitten you*.

The gates are `> 2` wound, `> 4` pain/burn/deep, `> 6` stitch, `> 8` wound
infection, so anything past 8 opens all of them; 10 says what it means.

Scanning another player is a **wrapper on `ISMedicalCheckAction.perform`**, not
a reimplementation, because that action also does the animation, the proximity
checks, the body-damage subscription, the window bookkeeping and the joypad
focus — all of which we would otherwise be copying and then failing to keep up
to date.

### The sweep

`C.SweepRadius` (40 tiles), `C.SweepPerTick` (96), `C.SweepIntervalMs` (3000),
`C.SweepBands` (0.33 / 0.66 of the radius).

**It must stay sliced.** A cursor and a fixed number per tick, for the same
reason the landing search is sliced: a pass over a horde in one frame is not
slow, it is a hard lock. Do not allocate inside the loop.

The interval is the other half of the limit and is easy to think redundant: a
sweep of three zombies finishes inside a single tick, so "one at a time" alone
would let the button be held down and chirp every frame.

The plot is **drawn, never placed** — nothing in it touches a world object, the
same rule the torpedo's flight follows. It is an `ISPanelJoypad` built from the
helm's own LCARS parts (`H.pill`, `TREKLcarsButton`, `H.P`), so changing the
helm's palette changes this too.

### The lock

`C.UnlockRange` (2 tiles) and `C.UnlockCooldownMs` (20 s), both measured on the
server. `Med.lockOn` decides what counts as a lock and is asked by **both**
sides — the client to offer the option, the server before it touches anything —
so they cannot disagree.

Widening it is mostly a matter of which Iso classes `Med.lockOn` accepts. What
must not widen is the padlock and safehouse refusal; see *The rules it obeys*.

### Where it is in the ship

Both sick-bay lockers stock `C.Loot.medical`; the **forward** one at 5,1
carries one of each instrument outright via `special = "medkit"` — the same
mechanism that puts four phasers in the locker at 5,6, generalised into a
`SPECIALS` table in `TREK_Build.lua`. Leaving them to the loot list is not
enough: the fill walks it from a rolling cursor, so four entries among
thirty-two can miss both lockers and the ship sails with no tricorder aboard.

`tests/test_layout.py` cross-checks every `special` in the layout against the
rules in `TREK_Build.lua` **both ways**, so a typo fails a test instead of
quietly stocking nothing.

### Adding a fifth instrument

1. `item` block in `trekshuttle.txt` (`DisplayCategory = FirstAid` or `Tool`),
   borrowing a vanilla `StaticModel` / `WorldStaticModel`.
2. Icon through the Gemini toolkit on flat magenta → `tools/key_icon.py` →
   `tools/vet_icons.py` at 32px **against the rest of the set** → hand the
   sheet to `analyze-image`. Raws and the sheet go in `design/art/medical/`.
   **64×64**, because nothing here carries an `AttachmentType`.
3. `C.<Name>Item` and `C.<Name>Type` in config — two names for one item,
   because the recursive inventory lookup compares the **bare** type and
   everything that spawns or places it wants the full id.
4. `ItemName.json`, `Tooltip.json`, and every `IGUI_TREK_` string it asks for.
5. A menu option in `M.fillInventoryMenu` (or `M.fillWorldMenu`).
6. `C.Loot.medical`, **and** `SPECIALS.medkit` in `TREK_Build.lua` if the ship
   should be guaranteed one.
7. Bump `C.BuildRev`.
8. A `medical()` case, and mutation-check it.

---

## The rules it obeys

Not optional; `MULTIPLAYER.md` has the reasoning.

- **A character's body belongs to the client that owns them.** Treating
  yourself and reading your own vitals need no protocol at all — the same rule
  and the same reason as "a client moves only its own character". Treating
  *somebody else* is the EMH's, later, and will be a server command.
- **A lock is world state, so the server opens it.** A client is a request and
  never a fact: the tool is checked in that player's inventory **on the
  server's own copy**, and so are the range, the cooldown and the chunk.
- **The engine's own sync is not symmetric.** `setLockedByKey` fires
  `IsoDoor.sync()` itself, behind `if (!GameServer.server)` — so the authority
  that owns world state is exactly the process where it does nothing.
  `obj:sync()` is the explicit call, and the server makes it.
- **Reading somebody's body goes through their consent.**
  `requestMedicalCheck` raises a yes/no on their screen and only a yes reaches
  the action. A mod that reads a player without asking is a different kind of
  mod.
- **The tricorder will not open a padlock, or anything inside a safehouse the
  asking player is not a member of.** Both are another player's property. A mod
  that picks them is a griefing tool on every server that installs it, with no
  setting to turn it off, because an owner would first have to know it was
  there.
- **No admin-only or `-debug`-gated calls.** `ISHealthPanel.cheat` is the
  obvious one in this area and is exactly that; assume there are more, because
  medical and admin overlap heavily.
- **Read the result back.** Every treatment is asked, fixed, and asked again. A
  setter that silently did nothing looks exactly like one that worked.

---

## Engine facts, established

With `tools/pzapi.py` (exists, public), a grep of vanilla Lua (may I call it)
and `tools/javadis.py` (**under what condition** — the one that matters). Do
not re-derive these.

| Fact | Where |
|---|---|
| `ISHealthPanel.cheat` is `false or getDebug()`; otherwise only `ISAdminPowerUI` sets it | `ISHealthPanel.lua:5`, `ISAdminPowerUI.lua:135,461` |
| `doctorLevel` is assigned once at construction and only ever read after | `ISHealthPanel.lua:973` |
| Doctor gates are `> 2` wound, `> 4` pain/burn/deep, `> 6` stitch, `> 8` infection | `ISHealthPanel.lua:633-830` |
| **`ISHealthPanel` IS an `ISPanelJoypad`** — stick navigation, A to act, B to close, all built in | `ISHealthPanel.lua:4,902-959` |
| `ISHealthPanel:new(patient, x, y, w, h)`, then `doctorLevel`, then `wrapInCollapsableWindow(title, false):addToUIManager()` | `ISMedicalCheckAction.lua:48-59` |
| `wrapInCollapsableWindow` sets `window.nested` to the panel | `ISUIElement.lua:1771` |
| Examining another player in MP goes through consent: `requestMedicalCheck(target, requester)`, and only a yes reaches `ISMedicalCheckAction` | `ISHealthPanel.lua:1942-1962` |
| `startReceivingBodyDamageUpdates` / `stopReceiving…` are handled by `ISMedicalCheckAction` and `ISHealthPanel:update()` themselves | `ISMedicalCheckAction.lua:73`, `ISHealthPanel.lua:381,416` |
| **`BodyPart.RestoreToFullHealth()` clears `bitten`, `biteTime` and `infectedWound`** along with the health | `javadis.py` |
| Full part health is **100.0** — the constant that method writes | `javadis.py` |
| Zombie infection is `BodyDamage.setInfected(boolean)`; a **wound** infection is `BodyPart.setInfectedWound(boolean)` | `pzapi.py` |
| `setWoundInfectionLevel(-1)` clears it; `0` is a wound merely not infected *yet* | `ISHealthPanel.lua:298` |
| A bite is `BodyPart.SetBitten(boolean)` — capital S | `pzapi.py` |
| **`setCut(false)` and `setScratched(false, x)` take an early-return branch** — write the flag, call `setBleeding(false)`, return. Every timer, trait and sandbox lookup is in the *true* branch, and no infection field is near either | `javadis.py` |
| `isCut()`, `scratched()`, `stitched()`, `bandaged()`, `getBandageLife()`, `haveGlass()`, `haveBullet()`, `getIndex()` all exist and are public | `pzapi.py` |
| `BodyPart.setBandaged` has **no vanilla Lua call site**; vanilla goes through `BodyDamage:SetBandaged(index, on, life, alcoholic, type)` and removes one with `(index, false, 0, false, nil)` | grep, `ISApplyBandage.lua:141` |
| `IsoDoor` / `IsoThumpable` / `IsoWindow`: `setLocked`, `setIsLocked`, `setLockedByKey`, `isLockedByPadlock` | `pzapi.py` |
| **Every vanilla Lua call site for those lock setters is `DebugContextMenu`, `AdminContextMenu` or the tutorial** — the tutorial is what says they work for an ordinary character | grep |
| **`setLockedByKey(b)` syncs itself only when `!GameServer.server`** | `javadis.py` |
| `IsoObject.sync()` is public and vanilla Lua calls it on both sides | `ClientCommands.lua:780`, `ISFluidContainer.lua:102` |
| `SafeHouse.isSafeHouse(square, username, true)` returns the safehouse **only when the named player is not a member of it** | `javadis.py`, `ISBuildUtil.lua:12,15` |
| `cell:getZombieList()` works and this mod already uses it for the shields | `TREK_Core.lua:383` |
| `OnFillInventoryObjectContextMenu(playerNum, context, items)` is the mod-safe hook; an entry in `items` is either an `InventoryItem` **or** a stack table with its own `items` list | `ISInventoryPaneContextMenu.lua:935`, `ISRemoveItemTool.lua:348-358` |
| `character:playSoundLocal(name)` is public, with fifteen vanilla call sites, and does not put a noise on the map | `ISMap.lua:210` and others |
| `requestMedicalCheck` / `acceptMedicalCheck` are `LuaManager$GlobalObject` statics | `pzapi.py`, `ISWorldObjectContextMenu.lua:885` |
| **`rawequal` has no vanilla Lua call site anywhere in build 42** — and Kahlua is already missing `next` and `math.huge`. Compare usernames, not identity | grep |

### The treatment setters

```
setBleeding(false) / setBleedingTime(0)                bleeding
setCut(false) / setCutTime(0)                          a laceration
setScratched(false, false) / setScratchTime(0)         a scratch
setDeepWounded(false) / setDeepWoundTime(0)            deep wounds
setInfectedWound(false) / setWoundInfectionLevel(-1)   an ordinary infected cut
setBurnTime(0) / setNeedBurnWash(false)                burns
setFractureTime(0) / setSplint(false, 0)               fractures, and the splint
setStitched(false) / setStitchTime(0)                  stitches
BodyDamage:SetBandaged(i, false, 0, false, nil)        the dressing
setAdditionalPain(0)                                   pain
setStiffness(0)                                        stiffness
SetHealth(100)                                         the part's health
SetBitten(false)                                       *** never called here ***
BodyDamage:setInfected(false)                          *** never called here ***
```

---

## Testing

`tests/test_multiplayer.py::medical()` covers: the ship carries one of each
instrument **with the four taken out of the loot list first**, so it is the
`medkit` rule being tested and not a coincidence of cursor position; every item
offers a way to use it *through the menu*; a dose treats everything it claims
and leaves the bite and the infection alone; a dose is never spent on a healthy
player; an empty hypospray is shown greyed and refuses; the ship refills it and
the field does not; a regenerator pass closes skin, strips the dressing, and
does **not** touch the injected half, a bite, the infection, or a bitten limb's
bandage; it skips a wound with glass while still treating the rest and says so;
it works for ever; the health panel opens at doctor level with
`ISHealthPanel.cheat` still false; the sweep is sliced, banded and rate-limited;
and the lock override is a server command that refuses a padlock, a safehouse,
a target out of range, and a second try inside the cooldown.

`medical_multiplayer()` adds the two-client half: a player carrying no
tricorder is refused by the server, the one carrying it is not, the lock is
synced, **the asking client never writes the lock itself**, and scanning
another player asks their permission before any panel opens.

`tests/test_helm.py` drives `TREKTricorderWindow` the way it drives the helm —
several frames, every draw checked against the panel bounds, contacts placed
exactly on the range limit (which is where a plot goes outside its own box),
an empty sweep, and the controller.

**Mutation-check anything you add.** Twenty-nine mutations are known to be
caught -- fourteen across the set, eight on the regenerator, five on the
contact plot, one on the `special` cross-check and one on the sweep interval; there is no mutation runner in `tools/`, so write one in the
scratchpad. Five that were *not* caught on the first attempt, all worth not
repeating:

1. **A stale menu.** The hypospray's label carries the dose count, so a test
   that built the menu once and clicked it twice silently clicked nothing the
   second time. `click()` now fails if the option was not there.
2. **A cooldown masking three other guards.** The safehouse, range and padlock
   refusals all passed with their code deleted, because the override cooldown
   from an earlier check was still running. `cooled()` runs the clock on first.
3. **A slice count derived from the thing under test.** The sweep put
   `C.SweepPerTick * 3` contacts in front of the slicer, so raising the
   constant moved the test with it. It is a flat 400 now.
4. **A refusal that was really an unloaded chunk.** The out-of-range door was a
   hundred tiles away, so the server refused it for not being streamed in and
   the range bound was never reached. It is six tiles now — outside
   `C.UnlockRange`, inside the loaded area.
5. **A guard whose branch was never entered.** The "some healed, one
   obstructed" path was never reached, because the test put a single glassed
   wound in front of it and the whole pass was refused up front. It takes two
   wounds with one of them glassed.

And one that is *not* a gap: wasting a dose needs **both** the
`needsTreatment` guard and the `counts.total == 0` guard removed. No
single-line mutation reaches it, which is the intended redundancy.

---

## What will bite you

- **No hot reload.** Mod Lua loads when a world starts, and `.txt` script
  changes too. Every change needs a full restart.
- **New loot reaches new worlds only.** `C.BuildRev` is 15; an existing save
  keeps the lockers it has. Test in a fresh world (`DEV_GUIDE.md`, *Never
  restock an existing container*).
- **A convenience method is a bundle of writes somebody else chose.**
  `RestoreToFullHealth` is the case that nearly shipped here; read the
  disassembly before reaching for the short call.
- **The two infections have nearly the same name**, and the wrong one is the
  cure the whole game is built around.
- **`Med.lockOn` is asked twice, by two processes.** If you change what counts
  as a lock, both the offered menu option and the server's verdict move
  together — which is the point, but it means a change here is a change to
  what every client sees.
- **`U.batch`, not `U.try`, for anything per-part or per-tick.** A method that
  does not exist throws out of Java and dumps a stack trace *per call*; this
  mod has hit 2932 in one session. `Med.treatWith` batches per concern so a
  wrong name costs that concern and not the seven around it.
- **Kahlua is not Lua 5.1.** No `next`, no `math.huge`, and `rawequal` has no
  vanilla call site — do not lean on it.
- **The simulation can be kinder than the engine.** `pz_sim`'s
  `getAllTypeRecurse` returned an empty list to everything that asked until
  this feature needed it, which would have let a broken phaser sweep pass too.
  It models `setCut → setBleeding(false)` for the same reason. Keep it honest.
- **A test encodes an expectation, not a fact.** When something is reported
  broken, the tests covering it are suspects, not witnesses.

---

## Not built, and still to settle in game

Nothing here has been seen in the game. In the order worth checking:

1. **The four items are in the sick bay.** Fresh world, beam up, open the
   forward starboard locker.
2. **The hypospray.** Take damage, use it, read the halo note. Then the thing
   that matters: a bite must still be a bite afterwards and the infection
   moodle must still be there.
3. **The dermal regenerator.** Get cut and scratched, bandage one, then run it:
   the wounds close, the dressing comes off, no bandage was needed. Then the
   two refusals — a bitten limb keeps its bandage, and a wound with glass in it
   is skipped with a note saying why.
4. **The medical tricorder on yourself**, with a controller as well as a mouse.
   The panel is vanilla's and should already work on a pad; that is the claim.
5. **The sensor sweep**, somewhere with zombies in view: do the blips agree
   with what is actually around you, and does the framerate survive a horde.
6. **The lock override** on an ordinary locked house door, then on a padlocked
   one, which must refuse and say why.
7. **Two players**: the override from a client seen by the other machine; a
   scan requested and accepted; the refusal for a player carrying no tricorder.

Item 7 belongs to the two-player session pinned in `ROADMAP.md`.

**That open design question is answered, and the answer is the one this file
already guessed.** The medical tricorder reports everything a Doctor 10 sees —
wounds, pain, burns, stitches and *wound* infection — and still does **not**
reveal the zombie infection. The EMH does, in as many words, on the panel at
his station: he is the thing that knows, and he is also the thing that can do
something about it. A tricorder that announced "you are infected" with no cure
in reach would be a much harsher item; announcing it in the one room where the
cure lives is the whole point of walking aft.

**And one correction to what this file says above.** "A character's body
damage belongs to the client that owns them and syncs from there" is right for
your *own* body, and it is why the hypospray and the regenerator work
client-side. It is not a general rule. `BodyDamage.Update()` restores a
**remote** player's body to full on a client every single tick, so somebody
else's body does not exist on your machine to be read or written at all —
which is why every line of the EMH's treatment runs on the server and why its
panel has to *ask* what is wrong with the crewman on the biobed. See `EMH.md`
section 6.

---

## What would have bitten you

Kept because each generalises, and `DEV_GUIDE.md` cites two of them as the
cases that produced its rules.

### `BodyPart.RestoreToFullHealth()` cures a bite

**The one that was nearly shipped.** It is the tidy way to mend a limb, it is
public, it has eight vanilla Lua call sites, and its bytecode does considerably
more than mend it:

```
  1  ldc_w  100.0     putfield BodyPart.health
 37  fconst_0         putfield BodyPart.biteTime
 42  iconst_0         putfield BodyPart.bitten        <-- here
 92  iconst_0         putfield BodyPart.infectedWound
```

The hypospray is specifically decided **not** to cure a bite — that cure is the
EMH's and is the only reason the EMH is worth building — so the convenient call
silently hands a pocket item the one thing the game is built around, makes the
next roadmap item pointless, and **reports nothing at all**. It is not a bug
anybody would see. It is an item that is better than intended.

So this file's code sets the fields it means to set, one at a time, and never
uses the short call. The rule generalises past this one method: anything whose
name is a *summary* is a bundle of writes chosen for somebody else's feature.
`tools/javadis.py` lists what is in the bundle.

### `ISHealthPanel.cheat` works for the developer and for nobody else

```lua
ISHealthPanel.cheat = false or getDebug()     -- ISHealthPanel.lua:5
```

On under `-debug`, off otherwise, and the only other things that set it are the
admin panel and `isHealthCheat()`. It is the obvious way to build a tricorder
that ignores Doctor skill, and it would have worked on this machine and done
nothing for every Workshop subscriber — the `setGodMod` failure shape from
`DEV_GUIDE.md`, *The jar is not the API*. `doctorLevel` on the instance is the
real lever, and `medical()` fails if anything sets the global.

### A setter's own sync can be one-sided

`setLockedByKey(b)` really does fire `IsoDoor.sync()` itself, which makes it
look like the whole job:

```
 21  invokevirtual  IsoDoor.setIsLocked(Z)
 24  getstatic      GameServer.server
 27  ifne           -> 55            <-- on a server, skip the sync entirely
 43  invokevirtual  IsoDoor.sync(3)
```

A lock is world state, so by this project's first rule the server is what
changes it — which is exactly the process where that branch does nothing. The
door would have opened on the server and stayed shut on every screen.
`obj:sync()` covers both directions.

**"It syncs itself" is a claim about one side.** This mod has now been bitten
by both faces of it: `addFluid` really does sync from the server, and a
vehicle's mod data really does not reach clients at all.

### `MEDICAL_SET.md` was wrong twice, in the mod's favour

This file used to say `ISHealthPanel` is *not* an `ISPanelJoypad` and that the
controller question needed settling before anything was designed around it. It
is one, with stick navigation, A and B already in it, and vanilla's own medical
check hands it the focus. Nothing was needed.

It also said a lock change belongs on the server and stopped there, which is
right about authority and silently wrong about the packet.

Both were written from `pzapi.py` and a grep, without a disassembly. The three
tools answer three different questions, and the third one is the one that keeps
being the difference (`DEV_GUIDE.md`, *Verify engine methods before calling
them*).
