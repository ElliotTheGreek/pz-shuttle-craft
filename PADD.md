# The PADD

The working guide for the Personal Access Display Device, in the shape
`ENSIGN.md`, `PROBES.md` and `UNIFORMS.md` use: what the player does, the
engine facts it rests on, the one decision that shapes all of it, how each
piece works, and what is still to see in a game.

**Phase one is built and played. Phase two, section 12, is built** (2026-09-24)
-- a full-screen surface, transcribed tapes, and the entire Adirondack channel --
and its first call has been seen in game. `COMMS.md` is its other half and the
two files have to be read together: **the channel's content, scheduling and
multiplayer authority live there; its surface lives here.** Section 12.8 is what
was built and how it differs from the spec above it.

**Built and played 2026-09-24**: books loaded, the character died, the PADD
was recovered off the body with its library intact. A finished title carries
vanilla's own green tick in the read list -- `media/ui/Tick_Mark-10.png`, the
mark the inventory draws beside a read book -- set as the option's
`iconTexture`. Section 7 is what was checked
before a line of it was written, and section 11 is the route to try it.

---

## 1. What the player does

1. **Find or make a PADD.** It weighs next to nothing. The ship issues a few,
   and the replicator knows the pattern from the first day like all
   Starfleet gear -- a replicated PADD comes out **blank**.
2. **Go where the books are** -- a school, a library, a bookshop, somebody's
   living room. With a PADD on you, right-click a book -- in your inventory,
   or on a shelf in the loot panel -- and choose **Load onto PADD**. A short
   scan, a tricorder-ish chirp, and the book is on the PADD. **The book stays
   where it was**: the PADD copies it and takes nothing.
3. **Read from it later, anywhere, as often as you like.** Right-click the
   PADD, **Read**, and pick a title from its library. Your character reads
   with the PADD in their hands, **five times faster than off paper**, and
   gets exactly what the book gives: the skill multiplier, the recipes, the
   boredom and stress, the title ticked off. Reading never uses a book up;
   every entry is a digital copy.
4. **Copy it.** With two PADDs on you, **Copy library to the other PADD** --
   for a friend, or as a backup. Handing someone a PADD is handing them the
   library.
5. **Lose it and you lose the books.** They live on the PADD, not on you. A
   PADD dropped or left in a car takes its library with it -- and **when you
   die it stays on your body like everything else you carried**, so a new
   character who goes back and recovers it gets every book back.

The pitch in one line: **an unlimited library that weighs 0.3**, paid for by
going and finding each book once.

---

## 2. What a book is in build 42

Read out of `shared/TimedActions/ISReadABook.lua` (42.20.4). A book is **not
just an item id**, and this is the fact the whole design turns on:

| What | Where it lives | What reading it does |
|---|---|---|
| **Skill books** (`SkillTrained`, `LvlSkillTrained`, `NumberOfPages`) | the item script | `addXpMultiplier(character, perk, multiplier, lvl, maxLvl)` in `complete()`, scaled by pages read |
| **Page progress** | **per character, per book type**: `character:setAlreadyReadPages(fullType, n)` | a half-read book resumes where *this character* left it, whichever copy they pick up |
| **Recipe magazines** | the script's `getLearnedRecipes()`, and on some copies `modData.learnedRecipe` | `character:learnRecipe(...)`, `getAlreadyReadBook():add(fullType)` |
| **Titled literature** (a novel, a comic) | **per copy**: `modData.literatureTitle` | `addReadLiterature(title)`; boredom, stress and unhappiness via `character:ReadLiterature(item)` -- once per title |
| **Print media** (flyers, newspapers) | **per copy**: `modData.printMedia.id` | `addReadPrintMedia(id)`, and optionally reveals map locations |

So a PADD entry has to store the **full type and the copy's own mod data**
(`literatureTitle`, `learnedRecipe`, `printMedia`) -- two copies of
`Base.Book` are different novels.

And three facts about the action itself:

- **`ISReadABook` is a networked timed action whose effects run on the
  server.** `complete()` checks `isServer()`, applies the multiplier, the
  recipes and the literature there, and then calls
  `sendSyncPlayerFields(character, 0x07)` (recipes, traits, books read) and
  `syncItemFields(character, item)`.
- **It needs the book in the reader's inventory.** `isValid()` is
  `getInventory():containsID(item:getID())` on a client.
- **Build 42 carries a mod's timed action over the network by name.**
  `NetTimedAction.set(player, action)` reads the action's `Type` from its
  metatable and its arguments by the **parameter names of its `new`**
  (`Prototype.locvars`), and the server rebuilds it. So an action defined in
  `shared/` can have a server half -- *in principle*; section 7 has it first
  on the list to prove.

---

## 3. The decision: how do you read a book that is not there?

Everything else is bookkeeping. Three ways, and the first two are wrong:

**A. Put the real book into their hands while they read, and take it back.**
The vanilla action runs untouched. But a real book in an inventory is a real
book: drop it, put it in a bag, die holding it, disconnect mid-read -- and the
PADD has duplicated a skill book. Every exit has to be closed, and a
duplicate that escapes once is a duplicate for ever. **Rejected.**

**C. Subclass `ISReadABook` around a hidden real book.** The same item, the
same exits, plus a class the engine may not rebuild on the server.
**Rejected.**

**B. The PADD's own reading action, with the book reconstructed only where
nobody can hold it.** Recommended.

- **`TREKReadPadd`**, in `shared/`, derived from `ISBaseTimedAction`, with
  `new(character, padd, entry)` -- the PADD is a real item in the inventory,
  which is what `isValid()` checks, and the entry is a number.
- **Duration** computed the way `ISReadABook:getDuration()` does it -- pages
  times the sandbox's minutes per page, the Fast/Slow Reader traits, reading
  glasses, sitting down -- and then **divided by `C.PaddReadSpeed` (5)**.
  The traits and the glasses still count; the PADD multiplies on top of
  them.
- **Anim and hands**: `setActionAnim(CharacterActionAnims.Read)`, and
  `setOverrideHandModels(nil, padd)` -- **the PADD is what is in their
  hands**, not a book.
- **The effects, in `complete()` on the server**, against a **detached
  instance**: `instanceItem(fullType)`, the stored mod data copied onto it,
  handed to the same engine calls `ISReadABook` makes -- `addXpMultiplier`,
  `learnRecipe`, `ReadLiterature`, `addReadLiterature`, `addReadPrintMedia`,
  `setAlreadyReadPages` -- and then dropped. **It is never added to any
  container**, so there is nothing to drop, bag, loot or keep. It exists for
  one function call as a bag of data the Java methods know how to read.
- Then `sendSyncPlayerFields(character, 0x07)`, exactly as vanilla.

**One deliberate difference from vanilla**: a skill book's multiplier is
granted when the read *completes*. Vanilla grants part of it as the pages go
by. An interrupted read still keeps its pages -- the progress is the
character's -- so the next read off the PADD resumes and finishes, and at
five times the speed that is a short wait.

The cost of B is that it duplicates `ISReadABook`'s arithmetic -- the
multiplier per level, the pages-read scaling, the too-high and too-low level
refusals -- and a patch that changes vanilla's leaves ours behind. That is
the right cost to pay: the alternative costs a duplication exploit. Keep the
copied logic in one function with a comment naming the vanilla lines it
mirrors, so it can be diffed when the game updates.

---

## 4. The library

**On the PADD, in its mod data**, a list of entries:

```lua
padd:getModData().TREKLibrary = {
    { type = "Base.BookCarpentry1", name = "Carpentry for Beginners",
      kind = "skill", skill = "Carpentry", level = 1, maxLevel = 2,
      pages = 220, fast = false },
    { type = "Base.Book", name = "The Last Train", kind = "literature",
      pages = 0, fast = false, md = { literatureTitle = "LastTrain" } },
    { type = "Base.MagazineCooking1", name = "Good Cooking Magazine",
      kind = "recipe", pages = 0, fast = false },
}
```

`kind`, `skill`, the levels and the page count are read off the real book
when it is loaded and kept, so the menus can group and grey without asking
the engine about an item that is not there. `TREK_Padd.lua` is the whole of
it: `Pd.entryOf`, `Pd.key`, `Pd.add`, `Pd.merge`, `Pd.erase`.

- **The item, not the player**, which is what makes "lose the PADD, lose the
  books" true without any code: mod data on an `InventoryItem` is saved with
  it and travels with it -- the hypospray's doses have lived that way since
  1.3.
- **Written on the server and synced**, the way vanilla's own
  `ISChangeFishingRodEquip:complete()` writes a rod's line: set the mod data,
  then `syncItemModData(character, item)`. That call exists
  (`GlobalObject.syncItemModData`) and has that ordinary, non-admin vanilla
  call site.
- **A duplicate is refused**: same type and same copy data.
- **Unlimited.** DEV_GUIDE's *a table transmitted whole cannot hold a list
  that grows* was the reason to ask, and the answer is that it does not bite
  here: the library is synced **only when it changes** -- a book loaded, a
  library copied -- never on a timer, and an entry is a type, a name and at
  most three short strings, about a hundred bytes. Five hundred books is
  about 50 KB sent once, when the five-hundredth is loaded. Entries are kept
  lean on purpose: nothing goes in one that can be read back off the item
  script (pages, skill, level).
- **The Read submenu has to cope with a big library**: grouped by kind
  (skill books by skill, then recipes, then literature) rather than one flat
  list of hundreds.
- **Page progress is not in the library.** It is the character's, keyed by
  book type, exactly as vanilla keeps it. Read half of *Carpentry Vol. 1* off
  a PADD, pick up a paper copy, and you resume at the same page -- for free,
  because that is how the engine already works.

---

## 5. The actions

| Action | From | Needs | Does |
|---|---|---|---|
| **Load onto PADD** | right-click a book in the inventory or loot panel | a PADD on you; the book in your inventory or a container within reach; not already on it | `TREKLoadPadd`, a few seconds with the chirp; server adds the entry and syncs |
| **Load N books onto PADD** | select several books in the loot panel, right-click | the same | one action per book, queued -- a school's shelf in one go. (A right-click on the bookcase itself is not built; selecting the shelf's contents does the same job.) |
| **Read** | right-click the PADD, submenu of titles | the PADD on you | `TREKReadPadd` (section 3) |
| **Copy library to ...** | right-click one PADD, submenu of your other PADDs | two PADDs in your inventory | `TREKCopyPadd`, time per entry; merge, no duplicates |
| **Erase** | right-click the PADD | -- | clears the library, with a confirmation |

Every right-click is **shown and greyed with a reason** when it cannot run --
no PADD, already loaded -- never hidden (DEV_GUIDE: *a correct
refusal nobody is shown is indistinguishable from a broken feature*).

Every item-list menu has to handle **both shapes** vanilla hands
`OnFillInventoryObjectContextMenu`: a bare `InventoryItem` or a stack table
with its own `items` (DEV_GUIDE failure signatures).

**What loads:** anything the engine calls literature with pages, a recipe or a
title -- skill books, recipe magazines, novels, comics, newspapers and
flyers. **Not** writable notebooks and journals (`canBeWrite()`): what a
player wrote in one is theirs, and copying it is a different feature.
**Not** maps: they are their own item type and the map panel is its own
system.

---

## 6. The item

- `TrekShuttle.TrekPADD`: weight **0.3**, `DisplayCategory = Electronics`, a
  hand model so it shows when read, a 64x64 icon.
- **The model is generated** (`tools/gen_padd.py`, off `MeshBuilder`) -- a
  slim slab with an LCARS screen -- and the icon rendered from it, the
  bat'leth's route, so the two cannot drift apart. It is the right shape for
  a script to describe: a box with a picture on one face.
- **Stock**: two, **issued in the armoury** beside the uniforms -- a
  `special` rule like theirs, guaranteed rather than rolled, which reaches
  new worlds only (*never restock an existing container*). The replicator
  knows the pattern from day one, so an existing save makes its own; a
  replicated PADD is blank.
- **No battery**, like the dermal regenerator. A PADD that needed charging
  would be a second chore on top of finding the books, for nothing.

---

## 7. Checked before building, and still to see in a game

**Settled from the bytecode**, and the architecture rests on these:

- **Every Lua timed action on a client goes to the server.**
  `LuaTimedActionNew.start()` calls `ActionManager.createNetTimedAction` on a
  client unless the action opts out (bci 60-101). A mod's action is no
  exception.
- **The server rebuilds it by its global class name**, with no allowlist:
  `NetTimedAction.parse` reads the type, `LuaManager.get(type)`, and calls
  its `new` (bci 75-167). So the classes are globals in `shared/`.
- **The arguments are the action's own fields, named after `new`'s
  parameters** -- `NetTimedAction.set` walks `Prototype.locvars` and
  `rawget`s each name. So every `new` here stores each parameter under
  exactly its own name. A field under another name reaches the server as nil,
  and the action never completes, silently.
- **Strings, numbers, booleans, tables, items and world objects cross**
  (`PZNetKahluaTableImpl.save`). A PADD, a book on a shelf and a string key
  all do.
- **`complete()` never runs on a client** (`LuaTimedActionNew.complete`,
  bci 34); it runs in single player and on the server. `perform()` runs on
  the client.
- **`syncItemModData(player, item)`** is a `GlobalObject` call with an
  ordinary vanilla call site doing exactly this job
  (`ISChangeFishingRodEquip:complete()`).
- **Vanilla applies a book's comfort twice in multiplayer** -- on the server
  in `complete()`, and on the reader's client through
  `literature.readLiterature`, which looks the book up by item id. A book
  read off a PADD has no id, so the PADD sends `paddRead` with the entry and
  the client rebuilds the book itself. Only on a server: in single player the
  two halves are one process.
- **`ReadLiterature` calls `Use()` on a `CONSUME_ON_READ` book**, so those
  are not loadable at all -- a reconstructed copy must never be used up, and
  a thing that is used up has no business being read for ever.

**Still for a game to answer:**

1. **The whole loop on the dedicated server** -- the class-name rebuild is
   read out of the bytecode and simulated, not yet watched.
2. **`syncItemModData` reaches the owner and survives a relog** -- load a
   book, disconnect, reconnect, read.
3. **A detached `instanceItem` is accepted by `ReadLiterature` and
   `addXpMultiplier`'s callers** on the server -- and is really detached: it
   must not appear in any container afterwards.
4. **`setOverrideHandModels(nil, padd)`** puts the PADD in the reading hand
   with `CharacterActionAnims.Read`, and it does not look absurd.
5. **The loot panel's right-click** on a book on a shelf reaches
   `OnFillInventoryObjectContextMenu` with the book, so loading does not
   require picking every book up first.
6. **Titles**: a titled novel loaded from one copy and read off the PADD
   ticks the same title in the literature panel (`ISLiteratureUI`) as reading
   the paper copy would.

7. **How the PADD sits in the hand.** The mesh lies flat, screen up, and the
   `Bip01_Prop2` attachment is vanilla's Book's six numbers as a first guess.
   Six numbers to judge in a fist, the blades' open question again.

---

## 8. Multiplayer, in one table

| What | Authority | Why |
|---|---|---|
| A PADD's library | **Server**, written in the load/copy action's `complete()`, pushed with `syncItemModData` | It is item state, and an inventory is server-authoritative in build 42's timed actions |
| What reading gives | **Server**, in `TREKReadPadd:complete()`, then `sendSyncPlayerFields` | Exactly where vanilla gives it |
| Page progress | **The character**, per book type, as vanilla keeps it | Nothing new |
| Menus, the title list | **Client** | Presentation |
| A novel's comfort | **Server and the reader's client**, as vanilla does it | The stats live on both; `paddRead` carries the entry |

A PADD is personal: two players cannot read the same PADD at once, because
it is in one inventory. Sharing is copying, or handing it over.

---

## 9. Decided (2026-09-24)

1. **Death**: nothing special. The PADD stays on the body like everything
   else, and a player who recovers it gets every book back.
2. **Loading copies**: the book stays where it was. A PADD entry is a
   digital copy, read as often as you like and never used up.
3. **Capacity**: unlimited (section 4 says why that is safe).
4. **Where the ship issues PADDs**: two in the armoury, beside the uniforms.
   (The books themselves are never "stored" anywhere but on a PADD.)
5. **Reading speed**: **five times faster** than paper, `C.PaddReadSpeed = 5`.

## 10. Not in this feature

- **Writing.** Journals and notes on a PADD are a different feature with
  different questions.
- **A ship's library.** The replicator's pattern store could hold books
  too, readable anywhere aboard. It would make the PADD's portability the
  point rather than its storage; worth considering once the PADD exists.
- ~~**Tapes and discs.**~~ **Reversed 2026-09-24** — transcription is phase two,
  section 12. A tape is still *played* on the television; the PADD *reads* it, and
  reading it does what watching it does (12.8).

---

## 11. Where things live, the checks, and the route

```
shared/TREK/TREK_Padd.lua          the library: what a book is, entries, keys,
                                   add / merge / erase, reach, read time,
                                   refusals, the rebuilt book, the comfort
shared/TREK/TREK_PaddActions.lua   TREKLoadPadd, TREKReadPadd, TREKCopyPadd,
                                   TREKErasePadd, and the paddRead handler
client/TREK/TREK_PaddUI.lua        the inventory menus
server/TREK/TREK_Build.lua         the armoury's `padds` rule
media/scripts/trekshuttle.txt      TrekPADD and its model
tools/gen_padd.py                  the mesh, texture, icon and render
```

**`tests/test_multiplayer.py`** `padd` and `padd_multiplayer`: the armoury's
two; no option without a PADD; notebooks and single-use fliers refused; a
load that copies and leaves the book; once only; out of reach refused; two
novels as two books and the same novel twice as one; the read time at a
fifth, with the traits first; a skill book's multiplier and its level
refusals; a novel's comfort once per title, from a book in no container; a
recipe magazine recorded; copy without duplicates; erase alone; a blank new
PADD. On two clients: the load rebuilt and completed on the server and
synced to its owner; a client unable to write a library; the multiplier on
the server only; the comfort on the server and the reader's client and
nobody else's.

`tests/pz_sim.lua` gained **timed actions modelled on the bytecode** --
single player runs all of it in one process, a client starts the action and
sends it by class name with its arguments read by `new`'s parameter names,
the server rebuilds and completes it, the client performs. The mod had never
had a timed action before, so the harness had never needed one.

**Seventeen mutations, one at a time, all caught**, including a `new` whose
parameter name does not match its field, a load that is never synced, a
rebuilt book put in the reader's pockets, and a multiplier applied on the
client.

**To try it, in a fresh world** (the armoury's two PADDs are new-world
stock; in an existing save, replicate one):

1. Beam aboard and take a PADD from the armoury, 3,0.
2. Go to a school, a library or a house with books. Open a bookcase in the
   loot panel, right-click a book: **Load onto PADD**. Select several and
   it offers to load them all.
3. Right-click the PADD: **Read from PADD** -> Skill books / Recipes / Books
   and magazines. Read one and time it against paper.
4. With a second PADD: **Copy library to...**. And **Erase PADD** on one.

What to look at: the PADD in the reading hand, the book staying on its
shelf, a titled novel ticked in the literature panel, and -- on the server
-- that a load and a read actually complete.

---

## 12. Phase two: the full-screen PADD

Specced 2026-09-24 and **built the same day**. 12.1-12.7 are the spec as written;
12.8 is what was built, including two things the author reversed while it was
being built. `COMMS.md` is the other half.

Phase one is a context menu. Phase two is **a screen** — because three things
arriving at once all want a surface, and none of them fits in a right-click
submenu:

1. **Transcribed tapes**, read as text rather than watched.
2. **The entire Adirondack channel** — the conversation, the options, the
   history.
3. **A library that is now two libraries and a shared record**, which a flat
   submenu cannot express.

### 12.1 The one decision: two libraries and a window

This is the fact the whole section turns on, and it is easy to get wrong because
phase one established the opposite.

| What | Lives on | Shared? | Lost with the PADD? |
|---|---|---|---|
| **Books** (`TREKLibrary`) | the item, in mod data | no — copy a PADD to share | **yes** |
| **Transcribed tapes** (`TREKTapes`) | the item, in mod data | no — same | **yes** |
| **The comms record** | **the server, once, for the ship** | **yes, to everyone** | **no** |

**A PADD is a container for the first two and a window onto the third.** Phase
one's whole pitch — *lose the PADD, lose the books* — stays true and must not be
quietly extended to the story: a player who drops their PADD in a warehouse has
not lost the plot. They have lost their books.

That is also the answer to the multiplayer requirement. One player advances the
channel; the record is the ship's; every other PADD shows it, because none of
them own it.

### 12.2 The history is replayed, not stored

**The comms record is the first unbounded growing shared list in this mod**, and
DEV_GUIDE's *a table transmitted whole cannot hold a list that grows* is aimed
squarely at it. A hundred conversations of rendered text is not something to put
in synced state.

So it does not go there. **The record stores the node ids that were visited and
the options that were taken — nothing else.** The text is regenerated from the
generated tree (`COMMS.md` 3) at display time, exactly the way a tape's lines are
translation keys rather than strings.

    { "TREK_COMM_FIRST_01", "TREK_COMM_FIRST_03:2", "TREK_COMM_FIRST_07:1", ... }

An id is a dozen bytes. Five hundred nodes is a few kilobytes, sent when it
changes and never on a timer. **The transcript is not data, it is a render** —
which also means fixing a typo in a line retroactively fixes every player's
history, and that is the right behaviour for a document nobody in the fiction
wrote down.

### 12.3 Transcription: a tape you can read

**Right-click a tape: *Transcribe to PADD*.** The tape stays what it is; the PADD
gains a text copy, in `TREKTapes`, keyed by the recording id.

- **You may only transcribe a tape you have watched to the end.** The engine
  already keeps per-character, per-line "have I heard this" state
  (`MediaLineData.getTextGuid()`, LORE.md 2), so *watched in full* is a question
  it can answer. This is deliberate: the PADD is **a record of what you have
  seen**, not a way to skip the television.
- **Reading a transcript grants nothing.** No codes, no XP, no boredom relief.
  The television is where a tape does something to you; the PADD is where you can
  go back and read what it said. One sentence, and it keeps the television's
  reason to exist intact.
- **A transcript is a render too.** Store the recording id, not the lines — same
  reasoning as 12.2, and it means a tape regenerated by `gen_tapes.py` updates
  every transcript of it.
- **Speaker colour survives.** The lines already carry r, g, b per voice; a
  transcript that drops them loses who is talking, which is most of what the
  tapes are doing.

**Why this matters more than it looks:** a forty-minute casualty list and a
twenty-two-item legal determination are documents, and documents want re-reading,
searching and quoting. `TREK_Wolf359` and `TREK_Uxbridge` are close to unusable
as television and excellent as text, and the six Tucker Gold fragments
(`LORE.md` 1c) are evidence a player will want to lay side by side.

### 12.4 The channel

**The PADD is the comms terminal. There is no console fitting.** This replaces
`COMMS.md` 5 and closes its open question about where a panel goes: the
*Adirondack* is in orbit, a PADD works anywhere on the surface, and the mod does
not need a new square in the cabin.

- **Full-screen**, or near enough — the transcript needs room and the option list
  needs to be readable without squinting.
- **Three views**: the **channel** (live, or idle with the last contact), the
  **history** (every thread, replayed), and the **library** (books and tapes).
- **A live call is the server's**, per `COMMS.md` 2: one player holds it, the
  others see it, everybody's PADD shows it.
- **Answering does not require being aboard.** A hail reaches a PADD in a
  Louisville warehouse, which is correct for the fiction and much better for
  multiplayer than making one player run home.
- **The option list is the only interactive part.** Everything else is a reader.

### 12.5 Deck and controller

**Assumption to confirm**: *deck compatible* means Steam Deck and gamepad, not
the ship's decks. Taken that way it constrains the design usefully:

- **Nothing is mouse-only.** The option list is navigable with a d-pad and
  confirmed with one button; the three views are shoulder-button tabs.
- **No hover-only information.** Anything in a tooltip is either on the face of
  the control or not needed.
- **Focus is always visible**, including on an empty list.
- **A timed node's clock is on screen**, not implied — `COMMS.md` 2's silence
  branch is a real outcome and the player has to be able to see it coming.
- Text at a readable size at 1280×800, which is the real constraint behind all of
  the above.

### 12.6 What this changes above

- **Section 10**: tapes are no longer out of scope. Writing still is.
- **Section 8**: the multiplayer table gains a fourth row — *the comms record:
  server, global to the ship, read-only on every PADD.*
- **Section 11**: new files. `client/TREK/TREK_PaddScreen.lua` (the surface),
  `shared/TREK/TREK_Comms.lua` (the tree and the record),
  `tools/gen_comms.py` (`COMMS.md` 3). `TREK_Padd.lua` gains `TREKTapes`.
- **Section 1's pitch is unchanged.** An unlimited library that weighs 0.3. The
  screen is how you read it, and the channel is a second reason to carry one.

### 12.7 Open questions

- **Does the screen open on right-click *Use*, or a keybind, or both?** A story
  surface a player has to dig through an inventory for will not get opened.
- **What a PADD with no library and no channel shows.** It is the first thing a
  new player will see and it should not be an empty box.
- **Whether a transcript can be copied between PADDs** like books can. Probably
  yes, same action, but it is a separate decision from the books.
- **Whether the history is readable before a player's first call.** A late joiner
  in multiplayer arrives to a story already in progress; showing them all of it
  immediately may be the right answer or may throw away every reveal at once.
- **Whether the six Tucker Gold fragments get a view of their own.** They are
  evidence rather than testimony, and a player will want them in order.

All six are answered in 12.8.

### 12.8 As built

**Files.** `client/TREK/TREK_PaddScreen.lua` (the screen, its notes and the key),
`shared/TREK/TREK_Comms.lua` (the stores, conditions and the renderer),
`server/TREK/TREK_CommsServer.lua` (the authority), the generated
`shared/TREK/TREK_CommsTree.lua` and `Translate/EN/Print_Text.json` from
`tools/gen_comms.py` + `tools/comms_threads.py`, and in `TREK_Padd.lua` /
`TREK_PaddActions.lua` the transcripts and `TREKTranscribePadd` / `TREKReadTape`.

**Opening it (12.7).** *Open PADD* is the first option on every PADD's inventory
menu -- which is also how a controller gets there on the Deck: select the PADD,
press A. Keyboard players also get a rebindable key, **K** by default, from build
42's own mod options (`PZAPI.ModOptions`, *Options -> Mods*). Vanilla reads
`ModOptions.ini` when its options screen is built, before any mod Lua exists, so
the screen re-reads it once the option is created -- or a rebound key would only
take effect after the options screen had been opened.

**The screen.** 1180x760 at most, never less than 900x600: inside a Deck's
1280x800 with room round it. Three views on LB/RB; X and Y step the list (or page
the channel's transcript); the transcript also has Up and Down buttons, because
the wheel is not a Deck's; B closes. Every control is registered once and hidden
when its view is not showing -- vanilla's `ISPanelJoypad` navigation skips
anything not `isReallyVisible()`, so visibility is what decides reachability. A
timed node shows its clock ("Silence in 23s"), counted from when the node reached
this client; the server's clock is the one that decides. The screen closes itself
when its PADD is no longer carried.

**What an empty PADD shows (12.7).** The channel view says she has not called
yet; the library says how to load a book or transcribe a tape. Never an empty box.
**A ringing call fills the box itself** -- the first play-test found it falling
through to "she has not called" while she was calling.

**Tapes -- reversed by the author while it was built.** 12.3 said a player may
only transcribe a tape they had watched to the end, and that reading a transcript
grants nothing. Both are gone:

- **Any tape** can be transcribed -- vanilla's and the mod's, watched or not. The
  tape stays where it was; the PADD gains its recording id.
- **Reading a transcript does what watching it does, once.** `TREKReadTape` feeds
  each line through vanilla's own interpreter, `ISRadioInteractions.checkPlayer`,
  with no source square: it records the line as heard *before* applying anything,
  so a line pays once per character whether it was heard on the television or read
  here, and it keeps the XP cut-off and the halos.
- **It is paced, not instant.** The interpreter debounces each code for thirty
  ticks per player; applying a whole tape in the last tick would fire one BOR and
  swallow the rest. The read applies its lines evenly across its length, a line's
  time is the television's (length / 10 * 60 frames) over the PADD's speed, and the
  per-line floor (`C.PaddTapeLineMin` 160) is set so that is never under thirty.
- **On the authority only**, like the television's own effects in multiplayer.
  The guard is in `applyTo` alone; `update()` runs on the client too.

**Transcripts copy (12.7)** with the books, in the same action, and an erase takes
both.

**The fragments get their own rows (12.7)**, in order, once the channel has
mentioned them: a transcribed one reads; one converted and not transcribed says
it is on the shelf; the rest say not recovered. The gap is the point.

**Late joiners see the whole history (12.7, decided).** The record is the ship's.

**What was learned, for DEV_GUIDE:** a translation category cannot be added by a
mod (`Translator.BY_NAME` is a fixed list, and keys route by prefix), so the
channel's text lives in `Print_Text.json`, which this mod did not have and
`gen_comms.py` owns outright; and `MediaLineData.getTranslatedText()` is
`Translator.getText(key)`, so a transcript renders straight from the `RecMedia`
table with no engine media calls at all.
