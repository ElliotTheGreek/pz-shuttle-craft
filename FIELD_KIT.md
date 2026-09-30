# The engineer's field kit

The working guide to the field kit: what it is, where each piece lives, how to
change it, the engine facts it rests on, and what will bite you. The shape is
`PHASERS.md`'s.

**Built 2026-09-30, not yet seen in game.** The author's brief: "a satchel
like bag with all the new starfleet tools that are lighter than normal tools
and have unlimited uses and stand in for other tools appropriately", and
self-sealing stem bolts "as a general nail replacement".

---

## 1. What a player gets

- **One Engineer's Field Kit in the armoury** (new worlds; `C.FieldKitIssue`).
  A satchel, worn like vanilla's, in Starfleet charcoal with a gold delta on
  the flap, carrying more for its weight than any vanilla bag
  (`WeightReduction` 90).
- **Inside it, five tools**, each lighter than the vanilla tool it replaces,
  none of which ever wears out:

| Tool | Stands in for | Tags |
|---|---|---|
| Sonic Driver | screwdriver, drill | `base:screwdriver`, `base:drillwood`, `base:drillmetal` |
| Hyperspanner | wrench, pipe wrench, pliers | `base:wrench`, `base:pipewrench`, `base:pliers` |
| Stem Bolt Driver | any hammer or mallet; takes barricades down | `base:hammer`, `base:clubhammer`, `base:ballpeenhammer`, `base:mallet`, `base:removebarricade` |
| Laser Cutter | any saw, tin snips, bolt cutters | `base:saw`, `base:smallsaw`, `base:metalsaw`, `base:sheetmetalsnips`, `base:boltcutters` |
| Laser Welder | blowtorch, and the welding mask | `base:blowtorch`, `base:weldingmask`, and every recipe's `[Base.BlowTorch]` |

- **A hundred Self-Sealing Stem Bolts**, taken wherever a recipe or a build
  asks for nails.
- **The replicator knows every one of them** (it learns every item this mod
  declares), so an existing world makes its own: the satchel, each tool and
  bolts by the quantity. A replicated satchel comes empty.

**What stem bolts do not reach: the barricade right-click.** It is Java
(section 5) and counts `Base.Nails` itself. Planks over a window still take
nails; everything in the crafting and build menus takes bolts.

---

## 2. Where everything lives

| What | Where |
|---|---|
| The items and their models | `media/scripts/trekengineering.txt` |
| The recipe patch, the sweep's rules, packing a kit; `TREK.FieldKit` | `media/lua/shared/TREK/TREK_FieldKit.lua` |
| The sweep, run by the authority | `media/lua/server/TREK/TREK_FieldKitServer.lua` |
| The armoury's issue | `TREK_Build.lua`, `stockFieldKit` and `SPECIALS.fieldkit`; `TREK_InteriorLayout.lua`, the armoury's `special` |
| Every number | `TREK_Config.lua`, section *The engineer's field kit* |
| Names and tooltips | `Translate/EN/ItemName.json`, `Tooltip.json` |
| Meshes, texture, icons, the satchel, its clothing XMLs and GUID rows | `tools/gen_fieldkit.py` |
| Review sheets | `design/art/fieldkit/`: `fieldkit_sheet.png`, `fieldkit_icons.png` (vs the set), `satchel_faces.png`, `satchel_vanilla.png` |
| Tests | `tests/test_multiplayer.py`: `field_kit()`, `field_kit_mp()`, and `single_player()`'s armoury check |

---

## 3. How it works

**A tool stands in by its tags.** Vanilla's recipes ask for most tools by tag
(`tags[base:hammer]` 140 times, saw 29, wrench 33, screwdriver 20...), so an
item carrying the tag *is* that tool to every recipe and every build. Nothing
in Lua is involved.

**Nails and the blowtorch are asked for by item id** (`[Base.Nails]` 110 times,
`[Base.BlowTorch]` 65, the torch's number being uses spent), which no tag can
answer. `FK.patchRecipes` walks every craft recipe's inputs when the world
loads (`OnGameStart`, `OnServerStarted`), and adds our item to each input's
item list that names what it replaces (`C.FieldKitStandIns`). Every process
loads the scripts itself, so each patches its own. It is idempotent, and it
logs what it did: `field kit: stem bolts stand in for nails in N recipe
inputs, the welder for a blowtorch in M`. **Finding no recipe that takes
nails is a WARN** and the patch tries again next time.

**Unlimited uses** is the phaser's rule. The authority (the server, or the one
machine in single player) walks each player's carried field tools every
`C.FieldKitSweepMs`, in pockets, in bags (the kit) and in both hands, and puts
their condition back to full and the welder's charge back to full, then sends
each one it changed to its holder (`syncItemFields`). `ConditionLowerChanceOneIn`
is 1000 besides, so wear between passes is rare. Only `C.FieldTools` are
touched: a vanilla hammer in the same hand is left alone.

**The issue** is a stock rule of its own, because `U.stockEach` puts items in a
locker and these go inside the bag: `stockFieldKit` makes the kit, packs it
(`FK.fillKit`, counted, a WARN if short), and puts it in the armoury, counted
again.

---

## 4. Changing it

- **What a tool stands in for:** its `Tags` in `trekengineering.txt`, then
  `FIELD_TOOLS` in `test_multiplayer.py`, which checks each tag is there and
  the weight is under the vanilla tool's. To see which tags vanilla asks for:

```sh
cd "/c/Program Files (x86)/Steam/steamapps/common/ProjectZomboid/media/scripts"
grep -rhoiE "tags\[[^]]*\] *mode:keep" . | sort | uniq -c | sort -rn | head -40
```

- **Another thing asked for by item id** (a second consumable to replace):
  a row in `C.FieldKitStandIns`. That is all the patch needs.
- **A new tool:** the item, a row in `C.FieldTools` (or it wears out) and
  `C.FieldKitTools` (or the kit does not carry it), a builder in
  `tools/gen_fieldkit.py`'s `TOOLS`, its words, and a `FIELD_TOOLS` row.
  Add its weight to `SIM.itemWeight` in `tests/pz_sim.lua`; the test fails if
  the two disagree.
- **The look:** `tools/gen_fieldkit.py TrekShuttle/42`, then look at
  `fieldkit_sheet.png`, and judge the icons against the set:
  `python tools/vet_icons.py design/art/fieldkit/fieldkit_icons.png SonicDriver
  Hyperspanner StemBoltDriver LaserCutter LaserWelder StemBolt FieldKit Backpack
  Phaser PADD Sentry Tricorder`. Icons are drawn 35% brighter than
  the model with a one-pixel dark outline, the phaser's rule; the satchel's
  at 90% brighter, because charcoal is right on a body and vanishes on the
  inventory's grey.

---

## 5. Engine facts, established

Read out of the bytecode on 2026-09-30. Don't re-derive them.

1. **An input's accepted items are `InputScript.itemScriptCache`**, a plain
   `ArrayList` made in the constructor (bci 105-112) and filled in
   `OnPostWorldDictionaryInit` (bci 576). `getPossibleInputItems()` returns it
   as itself, and `canUseItem`, which every craft asks, matches an item
   against it by name. So adding to it at load is adding to the recipe.
   Only an "any item" input wraps it (`PZUnmodifiableList.wrap(getAllItems())`,
   bci 507); that list already holds our items.
2. **`ScriptManager.getAllCraftRecipes()` is a plain getter** (no role or
   debug gate); its only vanilla call sites are under `DebugUIs/`, which is
   why it was read rather than trusted. `getInputs` and
   `getPossibleInputItems` have ordinary call sites in `ISBuildPanel`.
3. **The barricade menu is Java** (`ISWorldObjectContextMenuLogic
   .doBarricadeMenu`): it counts nails by `ItemKey` and wants an item whose
   type is `BlowTorch` for a metal barricade (`checkBlowTorchForBarricade`).
   No tag or list reaches it.
4. **`SyncItemFieldsPacket` carries condition and uses** (write, bci 26 and
   50) and finds the item through its own container, so a tool inside the
   satchel is reached; `processClient` sets both.
5. **The blowtorch tag is `base:blowtorch`** (`ItemTag.BLOW_TORCH`, string
   `BlowTorch`); only the vehicle menu reads it.
6. **Vanilla's held tools** (`Hacksaw.X`, `Blowtorch.X`) run their length up
   +Y from a grip near the origin, thin across X, with no hand attachment in
   their model blocks. Ours are built to that frame.

---

## 6. Testing

```sh
TREK_ONLY=field_kit,field_kit_mp,single_player python tests/test_multiplayer.py
```

**`field_kit()`**: every tool carries its tags and weighs less than vanilla's
(read from the installed game's scripts, with a floor on how many were read);
the stem bolts are lighter than nails, the welder is a drainable, the kit a
satchel that carries better than vanilla's; the simulation's weights and
capacity are the script's; a wall's nail input takes stem bolts after the
patch and not before, its planks' input does not, a weld's torch input takes
the welder, patching twice adds nothing, and a world with no nail recipe
WARNs and stays unpatched; a kit packs five tools and a hundred bolts; the
sweep finds the tools inside the kit, restores a worn driver and a spent
welder, leaves a vanilla hammer in hand alone, and waits its interval.

**`field_kit_mp()`**: the server restores its own copy, sends one sync per tool
changed, the holder's copy follows, and no client runs the sweep.

**`single_player()`**: the built cabin's armoury holds exactly one kit, with
105 items inside.

The sim learned bags with contents, per-item weights, drainable charge, a
recursive search that enters bags, `ScriptManager.instance` and craft
recipes shaped on `InputScript`, and an item sync carrying uses. **Eighteen
mutations, one at a time, seventeen caught.** Two were caught only after the
harness was made less kind: the any-item list was empty (it is the whole
catalogue), and the vanilla hammer was in a pocket, where the type search
already excludes it (the check on what an item is matters only in the
hands). The eighteenth is the any-item skip, which changes no outcome and is
kept for its cost; its comment says so.

---

## 7. What will bite you

- **A script file the asset test does not read.** `test_assets.py` kept a
  hand list of the mod's script files and reported every item in
  `trekengineering.txt` undeclared. It globs `trek[a-z]*.txt` now.
- **A thin tool's icon.** `gen_padd.icon_from` refuses anything under a fifth
  of its frame, which a screwdriver on the diagonal honestly is;
  `gen_fieldkit.trim_icon` has a floor that fits.
- **A badge placed in world space on two bodies.** The satchel hangs in a
  different place on each, so one world point hit 5% the same texels. The
  flap is one panel in the sheet, so the delta is drawn there, and the rig is
  asked only which way is up and whether those texels face out on both.
- **Shell heredocs** mangled two patches in this work, exactly as DEV_GUIDE
  says. Write the script to a file.

---

## 8. Open

- **Nothing of it has been seen in game.** First checks: the log line from
  the recipe patch; a wall from the build menu with only stem bolts; a weld
  with only the welder and no mask; the tools in hand during a craft (are
  they the right way up?) and lying on the ground; the satchel worn, in hand
  and dropped.
- **Barricading with stem bolts** would need an option of our own on the
  world menu, beside vanilla's. Not built.
- **A replicated kit comes empty.** Packing it on replication would be a
  rule in the replicator; not built.
