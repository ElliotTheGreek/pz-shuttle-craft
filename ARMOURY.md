# The Armoury

The working guide to the weapons that came after the phaser: the phaser
rifle, four cultures' energy weapons, the Starfleet holster, and the armoury
off the Adirondack's bridge that issues them. It follows `PHASERS.md`, whose
machinery every one of these weapons runs on.

**Built 2026-09-27, and played the same day**: the author's verdict was "it
works well, I like the new weapons". Which of section 9's checks that covered
was not itemised, so the list stands until each is confirmed.

`DEV_GUIDE.md`'s *Rules that exist because they were broken* and
`MULTIPLAYER.md` apply to every line.

---

## 1. What a player gets

| Weapon | Item | Hands | Bolt | Where |
|---|---|---|---|---|
| Phaser | `TrekPhaser` | one, holsters | orange | the shuttle's armoury; the Adirondack's armoury |
| Phaser rifle | `TrekPhaserRifle` | two, slings | orange, heavier | the Adirondack's armoury |
| Klingon disruptor | `TrekKlingonDisruptor` | one, holsters | green | a hideout (tube 1-2); the trophy case |
| Klingon disruptor rifle | `TrekKlingonRifle` | two, slings | green, heavier | a hideout (tube 1-2); the trophy case |
| Romulan disruptor | `TrekRomulanDisruptor` | one, holsters | cool green | a hideout (tube 3-4); the trophy case |
| Jem'Hadar polaron rifle | `TrekPolaronRifle` | two, slings | blue-white, heavier | a hideout (tube 4-5); the trophy case |
| Cardassian phaser | `TrekCardassianPhaser` | one, holsters | yellow | a hideout (tube 3-4); the trophy case |
| Starfleet phaser holster | `TrekHolster` | worn on the belt | -- | the Adirondack's armoury |

- **Every one of them is a phaser underneath.** The charge never runs down,
  they never jam and they never wear out, and every shot is a visible bolt
  in the weapon's own colour, seen by everybody nearby.
- **Only Starfleet's cut.** The phaser and the phaser rifle fell trees and
  burn out doors (`PHASERS.md` 1). A disruptor is a weapon and nothing more:
  it is not offered on the right-click, and the cut refuses one in hand.
- **Pistols holster, rifles sling.** Every sidearm has vanilla's pistol
  attachment, so it rides in the Starfleet holster and in every vanilla one
  (hip, left, shoulder, double). Every rifle slings across the back as
  vanilla's do.
- **Balance, roughly.** The phaser rifle is the phaser with twice the reach
  and a harder hit. The alien sidearms trade the phaser's quiet for damage.
  The alien rifles hit hardest and are the loudest things aboard. None of the
  alien arms is ever issued.

---

## 2. Where everything lives

| What | Where |
|---|---|
| Which weapons the phaser machinery serves, their bolt colours, which cut | `TREK_Config.lua`, `C.EnergyWeapons`, `C.energyWeapon` |
| The charge sweep, over all of them; the cut menu, cutters only | `client/TREK/TREK_Phaser.lua` (`P.carriedBy`, `P.cuttersBy`) |
| The cut's own check of the hand | `shared/TREK/TREK_PhaserCut.lua` (`PC.inHand`) |
| The bolts, per weapon | `client/TREK/TREK_PhaserFX.lua` (`energy`, `FX.bolt`, `drawBeam`'s tint and width) |
| The items, the holster, the five shot sounds | `media/scripts/trekshuttle.txt`, after `item TrekPhaser` |
| The six model blocks | `media/scripts/trekarms.txt`, **generated**, `module Base` |
| Meshes, textures, icons | `models_X/weapons/firearm/TREK_<Name>.x`, `textures/weapons/firearm/`, `textures/Item_TREK_<Name>.png` |
| The holster's clothing | `clothing/clothingItems/TrekHolster.xml`, `textures/clothes/trek/holster.png`, its row in `fileGuidTable.xml` |
| The armoury's stock, the hideouts' arms | `TREK_Adirondack.lua`, `A.Stock`, `A.StashArms`, `A.stockItems` |
| The armoury room | `tools/gen_adirondack_sections.py`, `SECTIONS["bridge"]` |
| Its furniture | `tools/adirondack_objects.py`, the last list: `arms_locker`, `trophy_case` |
| The hideouts' arms crates | `tools/gen_adirondack_tubes.py`, `ARMS_STASH` |
| Concepts, the jobs ledger, review sheets | `design/art/weapons/<name>/`, `design/art/weapons/jobs.json` |
| The bake (once per source) and the build | `tools/bake_arms.py`, `tools/gen_arms.py` |
| Vendored bakes | `tools/assets/trek_arms/<name>_baked.json` and `.png` (the raw GLBs are not committed) |
| Tests | `tests/test_multiplayer.py`: `armoury()`, and `adirondack()` and `jefferies()` for the stock; `tests/test_assets.py` for icons and models |

---

## 3. Holsters

Vanilla has two pistol attachment types. `Holster` is what vanilla's own
pistols carry, and `ISHotbarAttachDefinition.lua` routes it to *Holster
Right*, *Holster Left* and *Holster Shoulder*. `HolsterSmall` goes to those
three and the ankle holster. The phaser and the three alien sidearms are
`Holster`, like an M9. (`PHASERS.md` used to plan on `HolsterSmall`; the
game's pistols settled it.)

**The Starfleet holster is vanilla's belt holster in Starfleet grey.**
- Its model is vanilla's `M_/F_HolsterRight.x` and its slot `HolsterRight`,
  so vanilla's holster animations reach it where they expect.
- Its texture is vanilla's `holster_black`, remapped by brightness: the
  leather to charcoal and the stitch to gold (`gen_arms.build_holster`).
- **Its GUID row is merged into `fileGuidTable.xml`**, the table
  `gen_uniform.py` and `gen_species.py` share. Without it the holster equips
  and draws nothing, with no warning (`gen_uniform.py` says why).
- On the ground it borrows vanilla's `HolsterSingle_Ground`.

**An attachable item's icon is 32x32.** The hotbar draws it at
`slotX + width / 2` in a 60 px slot (`tests/test_assets.py`), so a 64 px icon
spills into the next slot. The phaser's icon was 64 while it had no
`AttachmentType`, and `gen_phaser.py` now draws it at 32 (and at 64 into
`media/ui/`). The holster provides a slot rather than attaching, so its icon
stays 64.

---

## 4. How the models are made

The phaser's pipeline (`PHASERS.md` 4), generalised:

1. **Concept.** Gemini (`generate-image`), one three-quarter view on white,
   the phaser's prompt shape. Each is an *original* design in its culture's
   look. The phaser rifle's first draw was a stubby carbine and was
   lengthened with `edit-image` (`concept_34_stubby_rejected.jpg` is kept).
2. **Mesh.** fal TRELLIS v2, seed 1701, texture 1024, 20 and 20 steps.
   Request ids and URLs are in `design/art/weapons/jobs.json`; the raws are
   17-20 MB each and are not committed.
3. **Bake.** `python tools/bake_arms.py` (pip: trimesh, fast_simplification,
   networkx, scipy, scikit-image). Once per source; see below.
4. **Build.** `python tools/gen_arms.py TrekShuttle/42`, on every build, with
   PIL and numpy only. It writes the meshes, textures, 32x32 icons, the
   holster, the five sounds, **`trekarms.txt`** and the review sheets.
5. **Look.** `design/art/weapons/<name>/<name>_sheet.png`: four views, the
   vanilla gun outlined over the side view **in the same frame**, the weapon
   at held size over four grounds, and the icon.

What the bake does, and why each step is there:

- **The frame is vanilla's, per kind.** A pistol goes into the M9's frame:
  barrel +Y, top -Z, grip toward +Z. Handgun03's `Bip01_Prop2` and `world`
  then fit it as they fit the phaser. A rifle goes into the M16's frame,
  which is **the other way up**: top +Z, grip toward -Z. It has no hand
  attachment at all, because the engine puts the mesh's origin in the fist,
  so the bake puts the origin on the pistol grip. The M16's grip was measured
  off its mesh: centred at y = -0.007, leaving the receiver at z = -0.012.
- **The turn is read off a picture.** TRELLIS returned each model its own way
  round: the Klingon pistol lay on its side, and the Cardassian faced
  backwards (its grip was at the muzzle end on the first probe). Each
  `WEAPONS` entry names the glTF axes its muzzle and top point along.
  `bake_arms.py --probe` draws every raw in its frame with a ruler along it
  (`design/art/weapons/arms_probe.png`).
- **The grip is found near a hint, and its top is found where the body
  begins.** `grip` is the pistol grip's place along the length from the
  heel, read off the probe's ruler. The join is found by walking up from the
  grip's foot to the first slice suddenly much longer fore and aft than the
  grip is thick. The first version measured the body's underside at a probe
  point instead. On the Klingon pistol that landed on the trigger guard and
  hung the weapon above the hand, and only the sheet showed it.
- **Slimmed and squatted into vanilla's bracket.** `across` caps the width,
  as the phaser was slimmed. `tall` caps a rifle's depth: the phaser rifle
  came out 0.25 tall against the M16's 0.14.
- **The palette is the concept's own.** The concept's object pixels are
  clustered, and the source's colours are moved onto the concept's
  statistics: TRELLIS's are darker and lit, and the Romulan's came back grey.
  The colour field is **blurred over the texture** before each texel is
  snapped. Snapping texel by texel painted the Klingon rifle in camouflage.
- **The emitter is found by its glow** in the front third, in the source's
  own texture: a Klingon emitter sits between two prongs, where the phaser's
  lens-by-geometry would paint the prong tips. Geometry (`lens`) is the
  fallback.
- **The muzzle attachment is the emitter the bake found**, written into
  `trekarms.txt` by `gen_arms.py`, so it cannot drift from the mesh.

**The sounds** are `gen_phaser.pulse` with its numbers as arguments
(`gen_arms.shot`). The rifle is a fifth lower and longer. The Klingon
disruptor snarls, low and buzzing, and the Romulan is a thinner falling
whistle. The polaron rises under a heavy knock, and the Cardassian is short
and bright. **Judge them by ear**; no test can.

---

## 5. How the weapons work

There is no new mechanism. `C.EnergyWeapons` lists every weapon the
phaser's machinery serves, by full id:

- **The sweep** (`P.carriedBy`) searches for each entry's bare type, so
  every energy weapon on the player is refilled, unjammed and repaired on
  the phaser's slow tick. `only` narrows it to one id.
- **The bolt** (`FX.bolt`) takes its `tint` and `width` from the entry.
  `drawBeam` draws a wider bolt by scaling its thickness and its impact
  spark. A cutting beam passes neither and is always the phaser's.
- **Cutting** is for entries marked `cuts`. `P.cuttersBy` is what the menu
  offers and draws. `PC.inHand` is what the action checks on the server, so
  a client that queues a cut with a disruptor in hand is refused with
  `NotHeld`, as before.

Nominal ammunition is `bullets_9mm` for pistols and `bullets_556` for rifles,
for the phaser's reason (`PHASERS.md` 3). Rifles are `boltaction` with no
`MagazineType`, so there is no magazine to lose.

**To add a weapon:** a concept, a TRELLIS job, a `WEAPONS` entry in the bake
and an `ARMS` entry in `gen_arms.py`. Then an item block with its
`AttachmentType`, an entry in `C.EnergyWeapons`, and its name and tooltip.
`armoury()` checks every entry's bolt and attachment type by itself.

---

## 6. The armoury off the bridge

Deck 1, in the corner the ready room left: a 4 x 5 room of deck plate,
`Armoury` (place tag `armoury`), through a sliding door in the bridge's east
wall.

| Piece | Where | Holds |
|---|---|---|
| `arms_locker` x3 | along the north wall, shared with the ready room | each: 2 phasers, a phaser rifle, 2 holsters |
| `trophy_case` | the south-west corner | one of each alien weapon |
| `science_station` | beside the door | nothing: the security console |
| `wall_sconce` | by the door | light |

- **The two new pieces are the last list in `adirondack_objects.py`, and new
  pieces always go last.** The furniture sheet numbers its tiles in that
  list's order, and a tile's number is its sprite name in every save. Placed
  mid-list, they renumbered every piece after them; the check that the 207
  existing tiles are pixel-identical is how that was caught. They are tiles
  207-210.
- **A save gets the room in place**: the layout's revision changed, and a deck
  is refitted to its layout when it next loads (`ADIRONDACK.md` 9).
- The Adirondack's security officers favour the armoury over the rest of the
  deck (`TREK_CrewServer`, `PREFER`).
- **The trophy case is not locked.** Build 42 has no lock for a container,
  so the case is a display you can open.

---

## 7. The hideouts' arms

Each hideout off the Jefferies tubes (`JEFFERIES.md`) had two `stash_crate`s.
The second one now has a name of its own (`gen_adirondack_tubes.ARMS_STASH`)
and holds the same stash and holosuite tape as before, **plus** one culture's
weapons (`A.StashArms`):

| Hideout | Crate | Weapons |
|---|---|---|
| tube 1-2 | `stash_arms_klingon` | Klingon disruptor, Klingon disruptor rifle |
| tube 3-4 | `stash_arms_romulan` | Romulan disruptor, Cardassian phaser |
| tube 4-5 | `stash_arms_dominion` | Jem'Hadar polaron rifle |

The contraband is unchanged: `jefferies()` checks the hideout still holds two
crates' worth of latinum. **Like the hideouts themselves, this needs a new
world**: a crate that is already stocked is never restocked.

---

## 8. Testing

```sh
TREK_ONLY=armoury,adirondack,jefferies python tests/test_multiplayer.py
python tests/test_assets.py
```

**`armoury()`**, single player:
- a disruptor alone is offered no cut, does not count as in hand, and the
  action refuses it;
- a phaser rifle in a pocket is offered the cut, drawn and fells the tree;
- the sweep sees all six and refills, unjams and repairs each;
- every entry's bolt is drawn in its own tint and width, and a vanilla rifle
  draws none;
- every pistol is `Holster` and every rifle `Rifle`, and the holster provides
  `HolsterRight`.

**`adirondack()`**: the three lockers hold 6 phasers, 3 rifles and 6
holsters; the case holds exactly one of each alien weapon.

**`jefferies()`**: the first hideout hides the Klingons' arms and nobody
else's, and still holds two crates' worth of latinum.

**`test_assets.py`**: every attachable icon is 32x32, and every
`WeaponSprite` names a model in `module Base` (it now reads `trekarms.txt`).

**Nine mutations, one at a time, all caught.** One was caught only after its
test was written: taking the stash out of the arms crate. Presence checks
could not see it, because the hideout's other crate still held one of
everything; the latinum count does.

---

## 9. Not yet seen

In one sitting, in a new world (the hideouts need one):

1. **In the fist.** Each pistol and rifle, drawn and aimed. Is the grip in
   the hand, and does the rifle sit on the shoulder? The rifles have no hand
   attachment and trust the origin; if one floats, move `grip` in
   `bake_arms.py` and rebake.
2. **On the ground**, dropped: the `world` attachments are Handgun03's and
   AssaultRifle's.
3. **The bolts.** Each colour on grass and on a pale roof, and the rifles'
   heavier bolts.
4. **The sounds**, by ear.
5. **Holstered and slung.** A phaser into the Starfleet holster and into a
   vanilla one; a rifle onto the back. Does the Starfleet holster draw on the
   hip?
6. **The armoury.** The door from the bridge, the lockers opened, the trophy
   case. Does the deck refit add the room to an existing save cleanly?
7. **The hideouts.** Each culture's crate.
8. **Two players**: another player's green bolt (`PHASERS.md` 8, *Other
   people's bolts*).

---

## 10. Open

- **The icons are dark.** The Klingon and Jem'Hadar arms are dark metal,
  true to their concepts, and at 32 px they are the dimmest in the set.
  `tools/vet_icons.py` would say how dim; the phaser's fix was a flatter,
  brighter angle.
- **No stun setting**, by the author's word (2026-09-27).
- **A thigh holster** would be the same item with vanilla's ankle model, if
  wanted.
- **The brig** from `ITEMS.md` 6's *Armoury / security office* is not built.
