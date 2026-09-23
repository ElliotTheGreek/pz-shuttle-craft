# The Starfleet wardrobe

The working guide for the mod's clothing, in the shape `REPLICATOR.md` and
`EMH.md` use: what the player gets, how to change each piece, the engine facts
not to re-derive, and what will bite you.

`ROADMAP2.md` section 1.4 is the design this came from. Its biggest open
question — *custom uniform mesh versus custom texture on vanilla geometry* —
is answered, and the answer made the rest small.

---

## 1. What the player gets

Six garments, three divisions each of two cuts:

| Item | Cut | Body location |
|---|---|---|
| `TrekUniformDutyCommand` / `Operations` / `Science` | one-piece duty uniform | `base:boilersuit` |
| `TrekUniformDressCommand` / `Operations` / `Science` | long formal dress uniform | `base:fullsuit` |

Command is red, operations gold, sciences teal. Each carries a combadge on the
wearer's left breast, a collar band at the throat and a grey undershirt
showing above it.

They reach the player three ways:

1. **The armoury locker** (3,0) is issued one of each — `special = "uniforms"`
   in `TREK_InteriorLayout.lua`, guaranteed rather than rolled. New worlds
   only: *never restock an existing container*.
2. **The replicator**, from the first minute of any save. `R.seedDefaults()`
   learns every id this mod declares on each authority start, so the uniforms
   need no migration and reach **existing saves** as patterns.
3. Later, the downed ensign of roadmap 1.7 will wear one.

They insulate (0.65 duty, 0.45 dress) and they are **not armour**. See §4.

---

## 2. How a garment is put together

A clothing item is five files and four joins:

```
media/scripts/trekshuttle.txt          item TrekUniformDutyCommand
    ClothingItem = TrekUniformDutyCommand
        -> media/clothing/clothingItems/TrekUniformDutyCommand.xml
             <m_GUID>                  -> media/fileGuidTable.xml
             <m_MaleModel>             -> the game's own rig
             <m_FemaleModel>           -> the game's own rig
             <textureChoices>          -> media/textures/clothes/trek/*.png
    Icon = TREK_DutyCommand            -> media/textures/Item_TREK_DutyCommand.png
```

**Everything except the item script and the icon is generated.**

```sh
python tools/gen_uniform.py TrekShuttle/42
```

writes the six textures, the six icons, the six clothing XMLs, the GUID table
and the contact sheet in `design/art/uniforms/`. The XML and the GUID row come
out of the same loop as the texture on purpose: the GUID is the one join that
fails *silently* (§4), so it is not a thing to maintain by hand.

To change a colour, edit `DIVISIONS` in `tools/gen_uniform.py` and re-run.
To change where a panel starts and stops, edit the `Garment` thresholds or
`_duty_colour` / `_dress_colour`, re-run, and **look at the sheet**.

---

## 3. Engine facts, so they are not re-derived

Everything here was read out of the installed 42.20.4 files or its bytecode.

- **A uniform needs no rigging.** Of the 1,795 clothing XMLs the game ships,
  597 have no mesh at all — shirts are textures painted on the body — and the
  rest share a small pool of rigs: 38 items ride `bob_trousers`, 7 ride
  `bob_boilersuit`. A garment is a shared mesh plus a 256×256 PNG.
- **No item uses both `m_BaseTextures` and `textureChoices`** — zero out of
  1,795. A garment is either a mesh with its own texture or a texture painted
  on the body, never both. That is why a skant has to be two items (§6).
- **The judge's robe is the only skirted rig with both bodies.** Every dress
  and skirt in the game has an empty model except `Skirt_Mini` (a skirt with
  no torso), `WeddingDress` (bridal neckline) and `BlackRobe`
  (`bob_judegsrobe` / `kate_judegsrobe`) — long sleeves, wrap front, flared
  skirt, and a full mask set.
- **A mod may ship its own GUID table.** `ZomboidFileSystem.loadFileGuidTable`
  walks `getModIDs()` and merges a `fileGuidTable.xml` from the mod's common
  dir *and* its version dir (bci 265–310), so `TrekShuttle/42/media/` is a
  supported location. `FileGuidTable.mergeFrom` is a plain `ArrayList.addAll`
  with **no de-duplication**, so GUIDs and paths must not collide with
  vanilla's — `tests/test_assets.py` checks both against all 1,795.
- **Both rigs are Y up, X the arm span, Z depth, and front is negative Z.**
  Rendered at yaw 0 the boilersuit shows its zip and pockets and the robe its
  V-wrap; at yaw 0 the near surface is the one with the smaller Z.
- **The wearer's left is +X**, and this was got wrong first time by deriving
  it (`left = up × forward = −X`) and putting the combadge on the wrong
  breast. The rigs carry a named skeleton and it answers outright: every
  `Bip01_L_*` bone weights vertices at positive x (`L_Hand` +0.369, `R_Hand`
  −0.369). **Ask the rig.**
- **Above 0.80 of the model's height the silhouette reaches 0.375; below it,
  0.15.** That is the T-pose arms, and it is the only thing separating a
  sleeve from a shoulder. Measured, not assumed.
- **`base:boilersuit` excludes everything but headgear and vests**, which is
  right for a one-piece. `base:fullsuit` is what `WeddingDress` uses.
- **Vanilla's `Boilersuit` carries `ScratchDefense = 10`.** It is deliberately
  not copied. See §4.

---

## 4. What will bite you

**A missing GUID row is invisible.** This is the whole reason the wardrobe is
generated and checked the way it is.
`OutfitManager.getClothingItem(guid)` calls `getFilePathFromGuid` and
**returns null at bci 12** when the merged table does not know the id. And
`loadFileGuidTable` reads each mod's table inside a catch that only reaches
`ExceptionLogger`. So a uniform whose row is missing or whose table failed to
merge still equips, still weighs 1.2, still insulates, still gets dirty and
draws **nothing at all**, with no warning anywhere in the log.

That is the sixth time this project has met the same shape — an unopenable
locker, a container handed items that were never created, a tap topped up
through an API it does not have, a menu hook that never ran, a weapon model
one module from where the engine looks. What has always caught it is *reading
the result back*:

```
TREK_Uniform()
```

reports, per garment, whether `getClothingItem()` came back at all and what
male model, female model and texture it carries. **Run it the first time the
mod is carried into a world.** The static checks prove the files agree with
each other; only this proves the engine found them.

**A texture painted in texture space will be wrong.** These atlases are
auto-packed, so a rectangle in the sheet is not a shape on the garment.
`gen_uniform.py` rasterises the rig's own UVs and decides every region, seam
and the badge from **world position**. The EMH's scanlines came out as wood
grain the one time this was done the obvious way.

**Both sexes share one texture.** `textureChoices` is a single path for both
models, so a texture right for one body can be wrong for the other — on a
character the author may never have made. The generator builds its region map
from *both* rigs and fails if more than 2% of shared texels land in a
different panel. The duty rigs differ at 0.97% (the collar sits 5 cm
off-centre on Bob and centred on Kate); the dress rigs at 0.00%.

*The first version of that gate measured the raw distance between the rigs and
failed the boilersuit at 0.077 — which was two bodies of different shape
sharing one layout, exactly what vanilla ships. It was measuring millimetres
when the question is which panel.* See DEV_GUIDE, *A guard is only as good as
the goal it was written from*.

**Unpadded UVs fringe.** Everything outside an island is transparent, and the
sampler does not respect island boundaries, so filtering along an edge mixes
the garment with nothing and puts a dark fringe down every seam — on the
sleeve heads and the collar, which is where a person looks. `dilate()` bleeds
the islands outward four passes.

**A stat can ride along from the block you copied.** Vanilla's `Boilersuit`
has `ScratchDefense = 10`. ROADMAP2 1.4 says the uniform carries no
armour-like protection, so it is not copied, and `tests/test_assets.py` fails
any mod clothing item that sets `ScratchDefense`, `BiteDefense`,
`BulletDefense` or `NeckProtectionModifier`. Insulation is not armour and is
allowed. The boilersuit's `RunSpeedModifier = 0.9` is likewise not copied to
the duty uniform — that number is there because coveralls are bulky, a
tailored uniform is not, and removing an unearned penalty is not a bonus. The
dress robe keeps it, because a floor-length robe really does slow you down.

---

## 5. Checks

| Check | Catches |
|---|---|
| `tests/test_assets.py` | every join in §2, both ways: an item whose XML is missing, an XML with no GUID row, a GUID that disagrees with the table, a GUID that collides with vanilla's or with another of the mod's, a row for a file that is not there, a model or texture not on disk, a garment with a model for one sex and not the other, a masks folder that is not a directory, a body location the game does not declare, and an armour stat |
| `tests/test_layout.py` | that the armoury's `special` list names rules `TREK_Build.lua` actually has, and that every rule is used |
| `tests/test_multiplayer.py` | that the ship sails with all six aboard, that `C.UniformIssue` is not empty, and that `S.uniformReport()` runs and resolves every one — including that a phaser answers *nil* to `getClothingItem()`, so the report cannot call anything at all a working garment |
| `tools/gen_uniform.py` | a region that came out empty, a combadge that covered nothing, and the two rigs disagreeing about what a texel means |
| `tools/vet_icons.py` | the six icons at 32px against the other twenty |

Sixteen mutations were run one at a time against these and all sixteen were
caught. One early mutation "passed" because its search text never matched the
file — the harness asserts the text actually changed now, because a mutation
that does not apply proves exactly nothing.

---

## 6. Not built, and still to settle in game

**None of this has been seen in a game.** In the order worth checking:

1. **That the GUID table merged at all.** `TREK_Uniform()` in a fresh world.
   Everything else is downstream of it.
2. **Both bodies.** Make a female character and look. One texture serves both
   and the male render cannot show the female one going wrong.
3. **Movement, sitting and the vehicle poses.** The rigs are vanilla and the
   animations are vanilla, so this should be free — worth ten minutes to
   confirm rather than assume.
4. **Dirt, blood, holes, wetness, washing and repair**, which come from the
   body location and the `BloodLocation` rather than from anything here.
5. **The armoury locker** holding one of each in a new world, and the log line
   `WARN uniforms locker holds 0 of 1 ...` never appearing.
6. **The replicator**, which should offer all six from the first minute of an
   existing save.
7. **Two clients.** Clothing replicates through vanilla's own
   `SyncClothingPacket` and there is no ship state here, so there should be
   nothing to do — confirm rather than assume.

## 7. Open, and deliberately not built

- **The skant** — the TNG season-one skirted uniform. `Bob_MiniSkirt.X` /
  `Kate_MiniSkirt.X` exist on `base:skirt` and coexist with a shirt, so it is
  reachable as tunic + skirt. The tunic would be a *body* texture (the 597
  route), which means rasterising the character mesh's UVs rather than a
  garment's — a second pipeline, and the reason this is a follow-on rather
  than part of the first pass.
- **Named outfits** (`media/clothing/clothing.xml`). Only needed to dress
  zombies, mannequins and spawned appearances. Roadmap 1.7's ensign is
  explicitly a static world model rather than a character, so this stays
  unbuilt until something actually needs it.
- **Rank insignia.** Cosmetic until a crew-role system gives it a purpose.
- **A wardrobe locker of its own.** The uniforms are in the armoury because
  the cabin has three Starfleet lockers and none of them is a slop chest. A
  fourth is a change to `design/buildinged/TrekShuttle_Interior.tbx` in
  BuildingEd, not to the Lua.
