# The replicator — implementation guide

A galley fixture with a searchable interface that materialises **any item in
the game**. Roadmap item 4, ahead of the EMH.

**Nothing is built.** Everything below is either an engine fact verified with
`tools/pzapi.py` and a grep of vanilla Lua, or a decision that needs taking
before code is written. Decisions are marked **DECIDE**.

`DEV_GUIDE.md` first, then `MULTIPLAYER.md` for the client/server split.
`MEDICAL_SET.md` and `PHOTON_TORPEDOS.md` are the two worked examples of a
feature built to these rules; this will end up in that shape once it exists.

> **Blocked on the interior refit.** The replicator is a *cabin fixture*, so it
> needs a square in `TREK_InteriorLayout.lua` and an entry in the `.tbx`, both
> of which are being rewritten right now. Everything except the placement —
> the catalogue, the UI, the protocol, the model — is independent of that and
> can be built first. **Do not touch the layout files until the refit lands.**

---

## The goal

Walk up to the replicator, open it, type what you want, and the ship makes it.

That is the fantasy, and it is a dangerous one: a button that produces any item
in Project Zomboid is a creative-mode cheat with a Star Trek skin. The whole
design problem here is keeping the *capability* universal — it really can make
anything — while keeping the game a game.

Three things this must be:

- **Universal.** Not a hand-written recipe list. It reads the game's own item
  catalogue, so it covers vanilla, future patches and other people's mods
  without a line of maintenance.
- **Legible.** The player must be able to see why they cannot have something,
  and what to do about it. A grey entry with a reason beats a missing one.
- **A server owner's choice.** On a public server this is an admin power. It
  ships with a sandbox option and a default that does not wreck anybody's
  world.

---

## DECIDE: what it costs

**This is the decision the whole feature hangs on, and it should be made before
anything is written.** The recommendation is in bold; the others are here so
the choice is a choice.

### Recommended: patterns, plus a sandbox option

**The replicator can make any item the ship holds a *pattern* for**, and it
learns a pattern by scanning one — put the item in the replicator (or hold it
and pick *Store pattern*) and the ship keeps it for ever.

Why this one:

- It keeps the capability honestly universal. Nothing is hand-listed; the limit
  is what you have found, not what somebody wrote down.
- It is a **progression mechanic rather than a tax**. Looting stops being
  "find supplies" and becomes "find the first one" — which is a genuinely
  different and still interesting game, and it is exactly what a replicator
  should do to a supply chain.
- It is canon without being twee: this is the transporter pattern buffer.
- It costs no new resource, no power bar, no second UI.
- It is **one set of strings in ship state**, which the crew share. Finding a
  bandage helps everybody.

With a per-use delay of a few seconds so it reads as a machine working rather
than a menu dispensing.

`TrekShuttle.Replicator`, three values:

| | |
|---|---|
| **Patterns** (default) | as above |
| **Unrestricted** | anything in the catalogue, immediately — for people who want the sandbox toy |
| **Off** | the fixture is scenery |

### The alternatives, and why not

- **Free and unlimited.** One line of code and it deletes the game. The mod
  already has free-and-unlimited items (the phaser, the torpedoes, the dermal
  regenerator) and they work because each does *one* thing. "Any item" is not
  one thing.
- **Energy budget.** A power reserve that drains per item, scaled by weight,
  recharging over time. More simulation, a bar to draw, a number to balance
  against every item in the game — and the thing it limits (how *fast* you
  cheat) is less interesting than the thing patterns limit (*what* you can
  cheat). Worth keeping as a later layer on top of patterns if the ship ever
  gets a power system; not worth it as the first mechanic.
- **Cooldown only.** Weak. You stand still for a minute and have everything.

---

## How it will work

```
client  walk up, right-click the fixture -> "Use the replicator"
        (a world-object context menu, the same event the lock override uses)

        TREKReplicatorWindow  (ISPanelJoypad, helm LCARS parts)
          ISTextEntryBox + onTextChange   -> filter
          ISScrollingListBox              -> name, icon, category
          category tabs / filter          -> a controller path that needs no typing
          "Materialise"                   -> Core.send("replicate", { id = fullType })

server  Net.onServer("replicate")
          alive / mayUse(player)                      the ship's own access rule
          sandbox: Off -> deny
          id is a string, sane length
          **the id is looked up in the real catalogue** -- Rep.catalogue()[id]
              not trusted from the client, and not instanceItem'd blind
          sandbox: Patterns -> ship state must hold that pattern
          cooldown
          instanceItem(id)                            the only creation path
          container:AddItem(item) + sendAddItemToContainer(...)
              or sq:AddWorldInventoryItem(...) if the fixture has no container
          Net.toClient("replicated", { id = ..., ok = ..., why = ... })

client  note, the sound, and the list refreshes
```

Storing a pattern is the mirror image: `Core.send("storePattern", { id })`, the
server checks the player really holds one, adds the id to ship state, commits.

---

## What it can make, and what it cannot

### The catalogue

`getAllItems()` returns every `Item` script in the game — vanilla, this mod,
and anything else installed. It is a **global** with non-debug vanilla call
sites, and `getScriptManager():getAllItems()` is the same list.

**The filter is vanilla's own**, and it is not optional:

```lua
if not item:getObsolete() and not item:isHidden() then ... end
```

That line is lifted from `ISItemsListViewer:initList()`, and it exists because
of the exact trap `DEV_GUIDE.md` already records: an **obsolete item is still
in the scripts and still returns nil from `instanceItem`**. Without the filter
the list fills with entries that look real and silently make nothing —
"present, drawn and inert", the shape this mod has paid for six times.

Vanilla's viewer also skips the **`Moveables` module** entirely. Those are the
pick-up-furniture placeholders; they are not things a player wants a replicator
to hand them.

### Also excluded

- **The mod's own spec-only items.** `TrekShuttle.TrekTorpedo` is a
  specification handed to `IsoTrap.new`, not something anybody holds. It is
  marked neither obsolete nor hidden and it *does* have a translated name
  ("Photon Torpedo"), so **the engine filter will not catch it** — it will
  appear in the catalogue, with no icon, offering the player a warhead. It is
  the proof that a hand-maintained blocklist is needed as well as the filter.
- **DECIDE: a design blocklist.** Vehicle keys, quest-ish items, other mods'
  internal placeholders. The hook should exist from day one even if it starts
  empty, because adding it later means adding it in a hurry.

### What is shown per row

`Item` gives the UI everything it needs, all public:

```
getDisplayName()      what the player reads
getFullName()         "Base.Axe" -- the id to send, and what instanceItem takes
getDisplayCategory()  grouping and the controller's browse path
getNormalTexture()    the icon, so the list is scannable rather than a wall of text
getModuleName()       "Base", "TrekShuttle", someone else's mod
getWeightWet/Empty()  if a cost model ever needs a number
```

---

## The interface

An LCARS panel, built from the helm's own parts (`H.pill`, `TREKLcarsButton`,
`H.P`) so the two consoles look like the same ship. `tests/test_helm.py`
already drives two panels and will drive a third.

- **Search** is `ISTextEntryBox` with `onTextChange` — the pattern
  `ISChat.lua:161` uses, so it is not a debug-only widget.
- **The list** is `ISScrollingListBox` with a custom `doDrawItem`, the way the
  helm draws its bookmarks: icon, display name, category on the right.
- **Every panel must work with a controller** (`DEV_GUIDE.md`). This is the
  hard part of this UI and it needs designing, not bolting on: **a pad has no
  keyboard**, so the search box cannot be the only way in. The answer is
  category tabs or a category filter that the stick can walk, with the text
  box as the mouse-and-keyboard fast path. Decide this before laying the panel
  out, or it gets retrofitted badly.
- **Filtering thousands of rows every keystroke** is the one performance risk
  in the UI. Build the filterable list **once** at open (id, lowercased name,
  category, icon) and filter that array — not the java list, and not
  `getAllItems()` per frame.

### The art

Same pipeline as the helm and the medical icons (`ROADMAP.md`, *How art gets
made*):

- **Gemini** (`generate-image` → `tools/key_icon.py` → `tools/vet_icons.py` →
  `analyze-image`) for the panel backdrop and any emblem, generated on flat
  magenta, vetted at the size it is drawn.
- Raws and the contact sheet go in `design/art/replicator/`, never only in
  `media/textures/`.
- A **sound**: the materialisation shimmer, added to `tools/gen_medical.py`'s
  sibling — or a new `tools/gen_replicator.py`. Synthesized, deterministic, and
  played with `playSoundLocal` so it does not call the dead over.

---

## The model

The fixture is a **world model**, the same as the helm console: a `.x` mesh
plus a texture, declared in `media/scripts/trekshuttle.txt` and placed with
`sq:AddWorldInventoryItem(C.ReplicatorItem, 0.5, 0.5, 0.0)`.

Two routes, and the second is new for this mod:

### 1. Procedural, like the helm

`tools/gen_helm.py` writes its mesh and texture from Python with
`tools/meshbuild.py`. A replicator alcove is a recessed box with a lit panel —
well within what that produces, and it stays reproducible from source with no
network.

### 2. Generated, through fal.ai — and the importer already exists

This is why the fal toolkit is worth reaching for, and the plumbing is already
in the repo:

```
Gemini or fal image model   a reference image of the alcove, one clean view
        |
fal-3d-trellis-v2 / fal-3d-hunyuan3d-v2 / fal-3d-triposr
        |                   image -> 3D. ASYNC: submit, then poll
        |                   fal-queue-status, then fal-queue-result
        v
   a GLB mesh URL
        |
tools/import_gltf.py        already reads glTF 2.0 binary: embedded buffers,
        |                   node matrices, indexed triangles, one diffuse
        v                   texture. No Blender, no third-party package.
   .x mesh + .png texture -> media/models_X, media/textures
        |
tools/preview_model.py      RENDER IT AND LOOK before the game ever runs
```

`fal-3d-triposr` is the cheap fast one for candidates (~15 s); TRELLIS v2 or
Hunyuan3D v2 for the one that ships.

**Three things to expect**, all of which `DEV_GUIDE.md` already warns about in
other words:

- **Generated meshes are not authored meshes.** Expect far too many triangles,
  a texture atlas laid out for a render rather than a game, and an arbitrary
  scale and origin. The importer gets it in; making it a *one-tile fixture at
  the right size, facing the right way* is still work. `tools/meshbbox.py`
  measures the result, and the bracket is whatever the helm console occupies.
- **Y is up** for PZ world models, and 1 unit is 1 tile. A GLB will almost
  certainly arrive Y-up but at a metre scale, so it needs scaling — the hull
  and the helm are the reference.
- **Render it and look.** Four separate faults in the hull were invisible in
  the source and obvious in one `preview_model.py` frame.

**Keep the generated source.** The reference image, the GLB and the render go
in `design/art/replicator/`; regenerating gets a *different* mesh, not the same
one again.

---

## Multiplayer

Straightforward, and it must not be cut corners on: **this is the one feature
in the mod that can hand a player anything in the game.**

| | |
|---|---|
| The item is created | **Server**, on a validated `replicate` command |
| Who may use it | **Server** — alive, and the ship's own `mayUse` (owner-and-crew respected) |
| The pattern set | **Server**, ship state, shared by the crew, transmitted like everything else |
| The sandbox setting | **Server** |
| The panel, the search, the list | **Client**, presentation only |

- **A client is a request, never a fact.** The id arrives from a client, so it
  is looked up in the real catalogue server-side before anything is created —
  never `instanceItem`'d blind on a string somebody sent.
- **`instanceItem(id)` works on the server**, and it is the only creation path
  this mod uses (`DEV_GUIDE.md`, *The jar is not the API*).
- **Items reach clients through the transmit calls**: `container:AddItem(item)`
  then `sendAddItemToContainer(container, item)`, or
  `AddWorldInventoryItem`.
- **Read the result back.** Count the container before and after, as
  `U.addVerified` does. A replicator that reports success and produced nothing
  is this project's favourite bug.

### The pattern set is the one thing to measure

It lives in ship state, which is transmitted whole on every change. A crew who
have scanned two thousand items are carrying two thousand short strings in
global mod data, and every `Ship.commit()` sends them.

That is probably fine and it is **not** something to assume. Measure it before
shipping: log the serialised size at 100, 1000 and "everything", and if it is a
problem the fix is to keep patterns out of `TREK_Ship` and give them their own
mod data key that is transmitted only when it changes.

---

## Where it goes in the ship

**Owned by the interior refit — coordinate before touching.** When it lands:

- a square in `TREK_InteriorLayout.lua` with a `tag`, in the galley;
- the fixture placed by `TREK_Build.lua` the way `furnishHelmItem()` places the
  helm console;
- `C.BuildRev` bumped, so **new worlds only** (`DEV_GUIDE.md`, *Never restock
  an existing container*);
- `tests/test_layout.py` will check it is inside the hull and not stacked on
  something.

---

## Engine facts, established

With `tools/pzapi.py` (exists, public) and a grep of vanilla Lua (may I call
it). Do not re-derive these.

| Fact | Where |
|---|---|
| `getAllItems()` is a Lua global returning `ArrayList<Item>`; `getScriptManager():getAllItems()` is the same list | `ISItemsListViewer.lua:42`, `forageSystem.lua:679`, `ISLiteratureUI.lua:363` |
| **The filter for a usable item is `not item:getObsolete() and not item:isHidden()`** | `ISItemsListViewer.lua:53` |
| An **obsolete item is still in the scripts and returns nil from `instanceItem`** — it looks exactly like a working entry that makes nothing | `DEV_GUIDE.md`, *Changing what is in a container* |
| Vanilla's own item viewer skips the **`Moveables`** module | `ISItemsListViewer.lua:71` |
| `Item.getDisplayName / getFullName / getDisplayCategory / getModuleName / getNormalTexture / getWeightWet / getWeightEmpty / getObsolete / isHidden` are all public | `pzapi.py` |
| `getFullName()` is the id `instanceItem` takes — vanilla pairs them directly | `ISFluidItemsViewPanel.lua:110,112` |
| `instanceItem(id)` is a `LuaManager$GlobalObject` static with 187 vanilla call sites, and works on the server | `DEV_GUIDE.md`, `MULTIPLAYER.md` |
| `IsoGridSquare.AddWorldInventoryItem(String, float, float, float)` returns the `InventoryItem` | `pzapi.py`, and `TREK_Build.lua:662` already uses it for the helm |
| `ISTextEntryBox:new(...)` with `.onTextChange` is the search widget, with a non-debug call site | `ISChat.lua:161,171` |
| `tools/import_gltf.py` reads glTF 2.0 binary — embedded buffers, node matrices, indexed triangles, float positions/UVs, one diffuse texture — with no Blender and no third-party package | this repo |
| fal.ai image→3D (`fal-3d-trellis-v2`, `fal-3d-hunyuan3d-v2`, `fal-3d-triposr`) is **async**: submit, poll `fal-queue-status`, then `fal-queue-result` for a **GLB** URL | the fal toolkit |

---

## What will bite you

- **Obsolete items.** Said twice on purpose. Skip the filter and the catalogue
  fills with plausible entries that make nothing, and the failure is silent.
- **The controller.** A search box is useless on a pad. Design the browse path
  into the panel from the start.
- **Filtering per keystroke.** Build the searchable array once at open.
- **Other mods' items.** The catalogue includes them, which is the feature —
  and it means the list contains ids this mod has never seen, with names it
  cannot predict and icons that may be missing. Nothing may assume an icon
  exists.
- **`C.BuildRev`** — the fixture reaches new worlds only.
- **No hot reload.** Every change is a full restart.
- **`U.batch`, not `U.try`,** for anything that loops over the catalogue. A
  wrong method name in a loop over two thousand items is two thousand Java
  stack traces.
- **This is the feature a server owner will be angriest about** if it ships
  with a permissive default. *Patterns* is the default for a reason.

---

## Build order

Each step leaves the mod working and is committed.

1. **The catalogue, headless.** `Rep.catalogue()` in `shared/TREK/` — build it
   once, filtered, sorted, with the searchable fields precomputed. A test that
   asserts it is non-empty, contains a known item, and **excludes a known
   obsolete one**.
2. **The protocol.** `replicate` and `storePattern` handlers in
   `TREK_Server.lua`, the pattern set in ship state, the sandbox option, and
   the `medical_multiplayer()`-style two-client scenario: a client with no
   pattern refused, the owner served, and no client ever creating an item.
   **No UI yet** — drive it through the commands.
3. **The panel.** LCARS, search, list, controller path. Extend
   `tests/test_helm.py` to draw it, and mutation-check.
4. **The item and the model.** Procedural first so the feature is complete and
   playable; the fal route as a second pass once it is known to work.
5. **Placement**, once the interior refit has landed.
6. **Art and sound**, vetted at the size they are shown.

---

## Open questions

Worth answering before step 2, not after.

1. **The cost model** — the DECIDE at the top. Everything else follows from it.
2. **How a pattern is stored.** Consume the item, or scan and keep it?
   Consuming is a real cost and reads as "the ship took it apart", which is
   what a replicator does. Keeping it is friendlier. *Recommendation:
   consume* — it makes the first one matter.
3. **Does the replicator hold a container?** Handing the item straight to the
   player's inventory is simpler; materialising it into a tray is more Trek and
   deals with a full inventory gracefully.
4. **Stack size.** One at a time, or a quantity field? A quantity field makes
   the cost model do all the work at once — worth having only if patterns are
   the gate.
5. **Does it need power?** The cabin has no power system today. If one ever
   arrives, this is its first customer.
6. **The design blocklist** — what, beyond obsolete, hidden and `Moveables`,
   should never appear.
