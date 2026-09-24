# The PADD

The working guide for the Personal Access Display Device, in the shape
`ENSIGN.md`, `PROBES.md` and `UNIFORMS.md` use. **Nothing here is built yet.**
This is the design, the engine facts it rests on, the one decision that shapes
all of it, and what to prove before writing code.

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
3. **Read from it later, anywhere.** Right-click the PADD, **Read**, and pick a
   title from its library. Your character reads with the PADD in their hands,
   for the time the book takes, and gets exactly what the book gives: the
   skill multiplier, the recipes, the boredom and stress, the title ticked off.
4. **Copy it.** With two PADDs on you, **Copy library to the other PADD** --
   for a friend, or as a backup. Handing someone a PADD is handing them the
   library.
5. **Lose it and you lose the books.** They live on the PADD, not on you. A
   PADD dropped, left in a car or stolen by a zombie horde's worth of bad
   luck takes its library with it. See section 9 for death.

The pitch in one line: **a skill-book library that weighs 0.3**, paid for by
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
  glasses, sitting down -- so a book takes as long off a PADD as off paper.
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
    { type = "Base.BookCarpentry1", name = "Carpentry Vol. 1", pages = 220 },
    { type = "Base.Book", name = "The Last Train",
      md = { literatureTitle = "LastTrain" } },
    { type = "Base.MagazineFirearms1", name = "Guns Monthly",
      md = { learnedRecipe = nil } },
}
```

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
- **Bounded** by `C.PaddCapacity` (proposed 40), because the table rides the
  item every time it is synced -- *a table transmitted whole cannot hold a
  list that grows* (DEV_GUIDE).
- **Page progress is not in the library.** It is the character's, keyed by
  book type, exactly as vanilla keeps it. Read half of *Carpentry Vol. 1* off
  a PADD, pick up a paper copy, and you resume at the same page -- for free,
  because that is how the engine already works.

---

## 5. The actions

| Action | From | Needs | Does |
|---|---|---|---|
| **Load onto PADD** | right-click a book in the inventory or loot panel | a PADD on you; the book in your inventory or a container within reach; room in the library; not already on it | `TREKLoadPadd`, a few seconds with the chirp; server adds the entry and syncs |
| **Load every book here** *(phase 2)* | right-click a bookcase | the same | one action per book, queued -- a school library in one go |
| **Read** | right-click the PADD, submenu of titles | the PADD on you | `TREKReadPadd` (section 3) |
| **Copy library to ...** | right-click one PADD, submenu of your other PADDs | two PADDs in your inventory | `TREKCopyPadd`, time per entry; merge, no duplicates, capacity respected |
| **Erase** | right-click the PADD | -- | clears the library, with a confirmation |

Every right-click is **shown and greyed with a reason** when it cannot run --
no PADD, library full, already loaded -- never hidden (DEV_GUIDE: *a correct
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
- **Stock**: two in the sick bay locker's neighbour -- which locker is a
  decision (section 9). The replicator knows the pattern from day one.
- **No battery**, like the dermal regenerator. A PADD that needed charging
  would be a second chore on top of finding the books, for nothing.

---

## 7. Verify first, in this order

Each of these is a claim the design leans on that no static check can
answer.

1. **A mod timed action runs its server half in multiplayer.** The bytecode
   says `NetTimedAction` rebuilds an action by its `Type` and `new`
   parameter names; prove it with the smallest possible action on the
   dedicated server -- a two-second `TREKLoadPadd` that writes one entry --
   before anything else is built on it. **If it does not, the fallback is a
   client-run action that ends in a server command**, which is how the EMH
   treats a body today.
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

Numbers 1 and 3 decide the architecture; do them before the model, the icon
or a line of menu code.

---

## 8. Multiplayer, in one table

| What | Authority | Why |
|---|---|---|
| A PADD's library | **Server**, written in the load/copy action's `complete()`, pushed with `syncItemModData` | It is item state, and an inventory is server-authoritative in build 42's timed actions |
| What reading gives | **Server**, in `TREKReadPadd:complete()`, then `sendSyncPlayerFields` | Exactly where vanilla gives it |
| Page progress | **The character**, per book type, as vanilla keeps it | Nothing new |
| Menus, the title list | **Client** | Presentation |

A PADD is personal: two players cannot read the same PADD at once, because
it is in one inventory. Sharing is copying, or handing it over.

---

## 9. Decisions for the author

1. **Death.** As designed, the PADD stays on the body like everything else
   you carried, and a new character who walks back and loots it gets the
   library back. If "die and lose the books" should be absolute, the PADDs
   on a dying character can be wiped on death -- one handler. Which?
2. **Does loading consume the book?** Designed as a copy, the book stays.
   Consuming it would make a PADD a pure weight-saver and remove the reason
   to visit a school twice.
3. **Capacity**: 40 titles, or unlimited, or more for a PADD made by the
   replicator than one found?
4. **Where the ship keeps them**: the armoury, the rations locker or the sick
   bay -- the three Starfleet lockers -- or a fourth, which is a BuildingEd
   change.
5. **A skill book off a PADD reads at the paper speed.** It could be faster
   (it is the future) or slower (small screen). Equal is the proposal.

---

## 10. Not in this feature

- **Writing.** Journals and notes on a PADD are a different feature with
  different questions.
- **A ship's library.** The replicator's pattern store could hold books
  too, readable anywhere aboard. It would make the PADD's portability the
  point rather than its storage; worth considering once the PADD exists.
- **Tapes and discs.** Vanilla's media are played on a television, which the
  cabin already has.
