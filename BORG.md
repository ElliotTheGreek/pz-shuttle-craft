# The Borg among the dead

Built 2026-09-27. **Not yet seen in game.** Section 7 is what to look at.

## 1. What it is

`LORE.md` already says what the horde is: the Founders' morphogenic virus and
Borg nanoprobes, grafted: *"a Collective with no Queen."* In most of the dead
the nanoprobes only keep a corpse walking. In a few they went on building, and
those are the Borg: about one zombie in two hundred at the default, as common
as a policeman.

| | What it looks like | How often it has it |
|---|---|---|
| **Assimilated** | a Kentucky civilian in the clothes they died in (vanilla's `Generic03`: a top, jeans, trainers), grey under the skin, dark veins from the eye, bald, the eyepiece and cranial plate | always |
| | the right forearm replaced by a tool | 30% |
| | a neck collar | 20% |
| **Drone** | a black exosuit, collar to toe, ribbed on the limbs and plated on the torso with green nodes; the same head | always |
| | chest armour, neck armour | 90%, always |
| | the prosthetic, left shoulder plate, left knee plate | 75%, 55%, 50% |

Both walk **upright and even, the living's walk slowed**, and stand still
rather than sway. They never run, whatever the sandbox's zombie speed. Nothing
else about them differs: they bite like any other zombie, and nothing about
them touches the cure (`TRAITS.md` 1, `EMH.md`).

Sandbox **Borg among the dead** (`TrekShuttle.Borg`): As common as police
(default), Scarce (x0.3), Common (x4), None. It is read when the world loads,
and it reaches zombies made after that; the dead already walking keep what
they are.

## 2. How, and why it is almost no code

**They are outfits.** A zombie's network packet carries its outfit id and
nothing more (`CREW.md`), so an outfit is the one thing about a zombie that
every machine already agrees on. The server picks it from vanilla's
`ZombiesZoneDefinition.Default` when the zombie is made, and every client
dresses it from the clothing definitions. There is no mod code in the look at
all, so there is nothing to go wrong in multiplayer.

Every piece is one of the engine's own mechanisms:

| Piece | Mechanism | Files |
|---|---|---|
| exosuit, grey skin | a texture laid over the body atlas (`m_BaseTextures`), as vanilla's T-shirt textures are, over whatever zombie skin is underneath | `textures/Body/trek/borg_{suit,skin}_{m,f}.png` |
| chest, neck, shoulder, knee armour | **vanilla's own skinned armour rigs** (cuirass, gorget, articulated shoulder, knee pad), re-textured as Borg plating. They bend with the walk, and they are what gives a drone its bulk | `textures/clothes/trek/borg_{cuirass,gorget,shoulder,knee}.png` |
| eyepiece and cranial plate | a static mesh on `Bip01_Head`, as vanilla's bunny ears are. Its `nohairnobeard` hat category removes the hair | `models_X/Skinned/Clothes/TREK_BorgHead_{M,F}.X` |
| prosthetic | a static mesh on `Bip01_R_Forearm`, as vanilla's vambraces are, with `m_Masks 6` hiding the right hand, as the ice-hockey gloves hide both | `TREK_BorgArm_{M,F}.X` |

All ten items are `hidden`, in `media/scripts/trekborg.txt`. Vanilla's
inventory pane skips a hidden item (*"they are just equipped models"*,
`ISInventoryPane.lua`), so a Borg's corpse shows its loot and not its
implants. None has a defence stat.

**The walk is the only code**, `shared/TREK/TREK_Borg.lua`, and it runs in
every process. It sets the walk type `TrekBorg` and the variable `TrekBorg`
on any zombie whose outfit is one of the two. The nodes that match them are
`common/media/AnimSets/zombie/{walktoward,walktoward-network,pathfind}/trekborgwalk.xml`
(Bob_Walk, speed 0.78) and `idle/trekborgidle.xml` (Bob_Idle). This is the
crew's method (`CREW.md`), keyed on the outfit instead of the mod's data, so
nothing is sent.

## 3. Changing it

Everything is generated: `python tools/gen_borg.py`. It writes the textures,
meshes, clothing XMLs, GUID rows, the item script, the item names and the
outfits (inside markers in `common/media/clothing/clothing.xml`, beside the
crew's), and the two sheets the look was judged on:

- `design/art/borg/borg_sheet.png`: vanilla, assimilated and drone, both sexes,
  three angles, at a frame of the walk;
- `design/art/borg/borg_game_scale.png`: the same at 64 and 100 pixels tall
  from the isometric camera, on grass, asphalt and at night. **Judge it here.**
  Detail that sells the close-up is invisible at game size. The eyepiece's
  lens was made half as big again for exactly that reason.

The sheets come from `tools/figure_render.py`: a vanilla body posed at one
frame of one of the game's animations, with skinned garments and bone-pinned
statics on it. Before trusting it with the Borg it was checked against
vanilla's own vambrace and bunny ears, which land on the forearm and the head.

| To change | Where |
|---|---|
| how many | `C.BorgDroneChance`, `C.BorgAssimilatedChance`, `C.BorgScale` |
| which piece, how often | `outfit_blocks()` in `gen_borg.py` |
| colours | the palette at the top of `gen_borg.py` |
| the walk's speed or animation | the three `trekborgwalk.xml` files |

## 4. Engine facts, not to re-derive

- **`IsoZombie.getOutfitName()` dresses the zombie** if it is still due a
  random outfit (`shouldDressInRandomOutfit`, bci 0-11). On a client that is
  an outfit of the client's own choosing, not the server's. `TREK_Borg` asks
  only once `shouldDressInRandomOutfit()` is false, and treats a nil name (a
  client's copy not yet dressed) as "ask again".
- **`HumanVisual.getOutfit()` is no way round it.** `Outfit` is not on the
  Lua exposure list.
- **A zombie's speed is its walk animation.** `doDeferredMovement` moves it by
  root motion, so replacing the walk sets the speed. That is why a Borg cannot
  run.
- **The engine recycles `IsoZombie` objects.** What `TREK_Borg` remembers is
  keyed on the persistent outfit id, and a body reused for an ordinary zombie
  loses the idle.
- **The Default list is rolled 0 to 100, in order, and stops at 100**
  (`getRandomOutfitInSetList`, called with `false` by
  `getRandomDefaultOutfit`). Vanilla's five Generic outfits are 20 each at the
  top, so they fill it: **an entry appended to the end is never picked**. The
  first build did exactly that and no Borg ever spawned. They go in first now,
  `B.reach` works out their real share by the same rule, the log line says it
  in per cent, and a WARN fires if it is zero.
- **Default is only for zombies no map zone claims.** A zone with its own
  definition (a trailer park, a restaurant) dresses its dead from that, so in
  some places the Borg share is lower than the headline.
- **`ZombiesZoneDefinition` is read once**, at the first pick (`checkDirty`),
  and cached. The entries are applied at load and again at
  `OnInitGlobalModData`, which comes before any zombie is dressed.
- **A dead zombie's worn items become its corpse's inventory**
  (`WornItems.setFromItemVisuals`, then `addItemsToItemContainer`), hidden
  ones included. They are in the container and not shown.
- **Any item with a hat category is "the hat"** (`ItemVisuals.findHat`)
  whatever its body location, and `HairStyles.getAlternateForHat` answers
  `nohair`/`nohairnobeard` with no hair.
- **`<m_MasksFolder>none</m_MasksFolder>`** is vanilla's word for no masks
  folder (290 files). `test_assets.py` used to read it as a missing directory.

## 5. What would have bitten you

- **Built 2026-09-27, first played the same evening: no Borg.** The entries
  were appended to the Default list, past the 100 that vanilla's Generic
  outfits already fill, so the engine's roll never reached them. The test had
  asserted only that the entries were *in the list*: true, and no evidence
  that anything could pick them. The simulation's list now opens with
  vanilla's Generic outfits and the test asks for the share the engine's roll
  gives. The mutation that appends them again is caught.
- A test run reported the crew section's *"stray zombies left aboard"* once.
  It fails about one run in eighteen **without this change too**; it is the
  crew churning during the check, not the Borg.
- The assimilated outfit is copied from vanilla's `Generic03` at generation
  time, minus hats, glasses, earrings, a nose stud, necklaces and bangles,
  which would sit where an implant goes. The copy refuses to write if it keeps
  fewer than three items or drops fewer than two, so a changed vanilla file
  cannot empty it silently.

## 6. Tests

- `tests/test_multiplayer.py`, section `borg`: both entries in Default once,
  at each sandbox value; the walk on a drone and an assimilated, not on an
  ordinary zombie or a crawler; never asking a zombie still due its random
  outfit; a zombie dressed late gets it; a recycled body loses it; and on two
  machines, the client decides only once its copy is dressed. Seven
  mutations, one at a time, all caught.
- `tests/test_assets.py`: the outfits' names match the config, every item
  GUID in them resolves, the three walk nodes and the idle match the walk type
  and variable, the head hides the hair, the arm masks the hand. Three
  mutations caught.
- `pz_sim.lua` gives every zombie an outfit (`ZedOutfitMT`), including
  `getOutfitName`'s side effect, so the test can see the mod never trigger it.

## 7. To see in game

Best in a **new world** with the sandbox's *Borg among the dead* on
**Common**. Walk into Muldraugh or any town: with a couple of hundred zombies
in sight, several should be Borg.

1. **They are drawn.** A drone is dark and armoured, with a grey bald head and
   a red eye; an assimilated is a civilian with a grey face, an eyepiece and
   a plate on the left of the skull. Nothing is invisible, floating or white.
2. **The pieces sit right.** The eyepiece over the left eye, the plate on the
   skull, the prosthetic on the right forearm with no hand showing through
   it, and the armour on the chest, neck, left shoulder and left knee.
   Women too.
3. **They walk upright** and slower than the others, stand still when idle,
   and do not sprint in a sprinter world.
4. **A dead Borg** keeps its look on the ground, and its corpse shows its
   pockets and none of the implants.
5. **On a server**, another player sees the same Borg.
6. **Sandbox None**, in a new world: no Borg at all.

If one looks wrong, or none come, grep `console.txt` for `borg:` (the per cent
of the dead the world loaded with, and a WARN if it is none) and `Failed to load asset` (a mesh or texture path).
