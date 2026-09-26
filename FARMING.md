# FARMING.md — hydroponics aboard the Adirondack

Grow alien crops in hydroponic trays aboard her, raise serpent worms in a tank,
and cook the species dishes from scratch: Earl Grey from a tea bush, Raktajino
from Klingon beans, plomeek soup, leola root stew, hasperat, roasted Andorian
tuber and live gagh.

The design rests on two research passes (2026-09-25), both summarised in
§8, and on one decision: **use vanilla's farming and crafting, not our own.**
- **Farming.** Vanilla farming works on any square once the server has
  plowed it, even though its dig menu refuses our deck. That gives us
  growth, watering, disease, harvest, seeds, save/load and multiplayer
  sync for nothing.
- **Cooking.** Build 42's crafting already has what these dishes need:
  drying racks, the mortar and pestle, evolved soups, and craftRecipes that
  pick up mod recipes automatically.

---

## 1. The loop

```
 seed locker ──► hydroponic tray ──► harvest ──► produce ──┬──► cook (stove / soup pot)
      ▲                 │  water, time                     ├──► dry (herb rack) ──► brew / grind
      └── seeds back ◄──┘  (seeding stage)                 └──► eat raw
 worm tank ──► feed scraps ──► serpent worms breed ──► gagh
```

**Why it matters to the player:**
- **Real food, not replicated.** Homegrown food carries no "replicated" mark.
  Klingons and *Real Food Only* characters take the replicated penalty
  (TRAITS.md). Real food is the cure, and this is the only place it grows.
- **Species comfort.** Every dish is somebody's home food (`C.SpeciesFood`).
  A Vulcan who grows plomeek and cooks the soup eats better than the
  replicator can make them eat.
- **Something to do aboard her** that is not fighting. Tend the trays, check
  on the worms, cook in the galley.

---

## 2. The crops

Seven crops, defined as vanilla crop types (`farming_vegetableconf.props`), with
Trek seeds, produce and sprites of their own.

| Crop (prop) | Species | Harvest | Kind | Used for |
|---|---|---|---|---|
| `TrekTeaBush` | Earth | tea leaves | perennial (`growBack`) | Earl Grey |
| `TrekBergamot` | Earth | bergamot fruit | perennial | Earl Grey, its zest |
| `TrekKlingonCoffee` | Klingon | coffee cherries → beans | perennial | Raktajino |
| `TrekPlomeek` | Vulcan | plomeek | annual | plomeek soup |
| `TrekLeolaRoot` | Talaxian | leola root | annual, root crop | leola root stew |
| `TrekAndorianTuber` | Andorian | tuber | annual, root crop | roasted Andorian tuber |
| `TrekHasperatPepper` | Bajoran | hasperat peppers | annual | hasperat |

The **Jumja stick** (Bajoran) and the **Orion wing-slug** are good later
additions: a jumja tree tapped for sap, and a second husbandry tank.

**The settings every crop gets:**
- `sowMonth` all year round. A ship has no seasons.
- `coldHardy = true`. The world's temperature is global, and a Kentucky
  winter would otherwise reach a starship.
- `isHouseplant = true`, and no bad or risk months.
- Growth times from vanilla analogues: tea from the herb table, root crops from
  potatoes and carrots, peppers from bell peppers.
- The perennials (tea, bergamot, coffee) use `growBack`: harvest them and they
  regrow from a middle stage instead of dying back to a stub.

---

## 3. The recipes

Every step uses a vanilla mechanism. New pieces are marked **new**.

| Dish (item already in the mod) | Chain |
|---|---|
| **Earl Grey** (`TrekEarlGreyCup`) | tea leaves → *herb drying rack* (`Tags = DryingRackHerb`) → dried tea. Bergamot fruit → *knife* → bergamot zest, which can also be dried. **new** craftRecipe `BrewEarlGrey`: a mug of water + dried tea + zest → `TrekEarlGreyCup`, which arrives filled with the mod's existing `TrekEarlGrey` fluid. An `OnCreate` sets it hot. The dried tea also gets `EvolvedRecipe = HotDrink:5`, so vanilla's *Prepare Beverage* works as a fallback. |
| **Raktajino** (`TrekRaktajinoMug`) | coffee cherries → *rack* → dried beans → roasted: cookable, in an oven → *mortar and pestle* or *stone quern* → ground Klingon coffee. **new** `BrewRaktajino`: a water mug + grounds → `TrekRaktajinoMug`. A second recipe tagged `CoffeeMachine` lets vanilla coffee makers brew it too. |
| **Plomeek Soup** (`TrekPlomeekSoup`) | plomeek has `EvolvedRecipe = Soup:15`, `EvolvedRecipeName = Plomeek`. A pot of water + plomeek on the stove names itself "Plomeek Soup", then *Divide into bowls*. |
| **Leola Root Stew** (`TrekLeolaStew`) | **new** craftRecipe: a pot + water + 3 leola root → `TrekLeolaStewPot` (cookable, like vanilla's `WaterPotRice`) → stove → divide into bowls. A fixed recipe, so the name cannot collapse into "Vegetables Stew". |
| **Hasperat** (`TrekHasperat`) | hasperat peppers (can be dried on the rack for a hotter version) + a vanilla tortilla or flatbread → **new** `MakeHasperat` (`AnySurfaceCraft;Cooking`). |
| **Roasted Andorian tuber** (`TrekAndorianTuber`) | the raw tuber is `IsCookable` (like a potato). Put it in the oven. |
| **Gagh** (`TrekGagh`) | live serpent worms (the worm tank, §4) + a bowl → **new** `ServeGagh`. Gagh is served live, so there is no cooking step. |

**How players learn these:**
- Recipes are learned from a **Starfleet botany PADD** (`LearnedRecipes`),
  found in the hydroponics lab. Cooking skill auto-learns them too
  (`AutoLearnAny = Cooking:3`).
- The crew's talk in hydroponics hints at them.

**The galley needs a heat source.** Her galley has counters and a sink but
nothing to cook on. We add a **galley range**: a Starfleet sprite
that is a real stove, powered the way the shuttle's oven is (TREK_Build's
`placeStove` and the power bus). The same galley also gets a mortar and
pestle and a drying rack. See open question 1.

---

## 4. The worm tank (gagh)

Serpent worms are the one animal aboard. The tank borrows vanilla composting's
own breeding, where fresh worms in a composter never rot and multiply as waste
composts (`IsoCompost.update`). But that is hard-coded to `Base.Worm`, so the
tank is our own:
- **The object:** a Starfleet worm tank. It is a tagged container on the
  deck, holding our item **`TrekSerpentWorm`**.
- **The rule:** a server `EveryHours` hook runs over the tanks on built decks.
  A tank with at least 2 serpent worms and some food waste in it (rotten
  food, scraps, meat) consumes some of the waste and adds a worm, up to a
  cap. A tank with no food lets its worms go hungry, then lose one a day.
  The tank never rots its worms.
- **The start:** the tanks start with 3 worms, so the loop runs from day one.
  Worms can be taken out and put in any tank.
- **Gagh:** `ServeGagh` takes 5 serpent worms and a bowl. Klingons love it.
  Everybody else takes the foreign-dish penalty, and the crew's talk has
  opinions.

---

## 5. Where it goes: Deck 5, Hydroponics

A new deck in the lift's list, built by the same pipeline as the others
(ITEMS.md §5.2). Later work can join it: the armoury, the Jefferies tubes
(winding crawlspaces, with a hidden area reachable only through them), and
the captain's quarters and labs.

| Room | What is in it |
|---|---|
| **Hydroponics Bay** (the big one) | rows of **hydroponic trays** under **grow-light panels**, a water feed point (a sink), a potting bench |
| **Botany Lab** | a **seed locker** (stocked with seeds of all seven), a **dehydrator** (the drying rack), a mortar and pestle on the bench, the botany PADD, a science station |
| **Serpent Tank Room** | two or three **worm tanks**, cool and dim, Klingon script on the wall |
| **Arboretum corner** | a few Earth and alien trees and a bench: somewhere to sit, and a place for the crew's quiet scenes |

The galley range (§3) goes on Deck 2's galley, where the cooking already is.

---

## 6. What has to be built

### 6.1 Art (the ITEMS.md §5.2 pipeline)

**New furniture**, each a manifest entry, concept, mesh, render and tiles:

| Piece | Size | Facings | Use |
|---|---|---|---|
| `hydro_tray` | 1×1 | 1 | the planter: a raised tray. **A crop grows on its square.** |
| `grow_light` | wall | W/N | light (look only) |
| `seed_locker` | 1×1 | W/N | container, stocked with seeds |
| `potting_bench` | 2×1 | W/N | counter container, stocked with tools and the mortar |
| `dehydrator` | 1×1 | W/N | the drying rack; see open question 2 |
| `worm_tank` | 2×1 | W/N | container (the gagh tank) |
| `galley_range` | 1×1 | WNES | a real stove |
| `arboretum_tree`, `alien_shrub` | 1×1 | 1 | look only |

**Crop growth sprites.** Vanilla uses 8 growth stages plus unhealthy, dying,
dead and trampled sprites. To keep the art affordable:
- **One mesh per crop** (a Gemini concept of the mature plant, then TRELLIS),
  rendered at **stage scales**: 0.2, 0.3, 0.45, 0.6, 0.75, 0.9, 1.0, and
  1.0 with fruit or flowers tinted in. The same plant visibly grows, which
  reads better than eight separate drawings.
- **Unhealthy, dying and dead** are the same render tinted yellow, brown and
  grey. **Trampled** reuses dead.
- The sprites are drawn to sit **in** the tray, so no `attachedFloor`.
  Their tile properties are only `BlocksPlacement`, and never the
  vegetation flags, which vanilla reads as weeds.

That is 7 crops × 11 sprites, about 80 tiles in a new sheet,
`trek_adirondack_03`. This is the biggest art job so far, and all of it is
automated.

### 6.2 Items (the ITEMS.md §5.1 pipeline)

| Kind | Items |
|---|---|
| Seeds (7) | `TrekTeaSeed`, `TrekBergamotSeed`, `TrekKlingonCoffeeSeed`, `TrekPlomeekSeed`, `TrekLeolaSeed`, `TrekAndorianTuberSeed`, `TrekHasperatSeed`. Each has a seed-packet pair, like vanilla's `PutSeedsInPacket`. |
| Produce (7) | tea leaves, bergamot, coffee cherries, plomeek, leola root, raw Andorian tuber, hasperat peppers. Food with `FoodType`, `DaysFresh`, `EvolvedRecipe` and `IsCookable` as §3 needs. |
| Processed (6) | dried tea, bergamot zest, dried coffee beans, roasted beans, ground Klingon coffee, dried hasperat peppers |
| Husbandry (1) | `TrekSerpentWorm` |
| Pots and learning (2) | `TrekLeolaStewPot`, a Starfleet botany PADD |

**Icons** for all of them come from the existing icon pipeline.
**Translations:** item names go in `ItemName.json`. A new
`Translate/EN/Farming.json` gets `Farming_<Crop>` for each crop, and
`Recipes.json` gets the recipe names.

### 6.3 Code

- **`server/TREK/TREK_Farm.lua`** (loads on both sides, as vanilla's
  farming config does):
  - **Registration.** Registers the seven props with all five sprite
    tables. `MOFarming` indexes all five and throws on a missing one.
  - **Trays.** A tray is ready to plant when the server has plowed it
    (`SFarmingSystem.instance:plow(sq)`). The deck builder primes every
    tray, and **Prime tray** in a tray's right-click menu re-primes one
    after a harvest, through a server command. Vanilla's own sow, water,
    harvest and cure then work on it in single player and multiplayer.
  - **The greenhouse rule.** Vanilla kills indoor crops unless their room is
    a greenhouse, and our deck has no rooms. A thin wrap of
    `SFarmingSystem.changeHealth` treats a plant on an Adirondack tray as
    a greenhouse: no indoor penalty, no rain, no winter.
  - **Hydroponic feed.** Trays are topped up with water every game hour, so
    tending means harvesting and replanting, not carrying water.
    Sandbox: *Hydroponics water themselves* (on by default).
- **The deck builder must not eat the crops.** `AS.buildDeck` strips every
  untagged object from deck squares, and a vanilla plant object is
  untagged. It must skip anything carrying farming mod data (`state`,
  `nbOfGrow`, `health`), or a rebuild wipes the bay.
- **Worm tanks:** the hourly breeding hook (§4), in `TREK_AdirondackServer`
  alongside the water top-up.
- **Recipes:** `media/scripts/trekfarming.txt` (module TrekShuttle, full
  `Base.` names, `base:` tags). `OnCreate` Lua goes in `lua/server` or
  `lua/shared`, and sends `sendItemStats` on a server.
- **Stock:** the seed locker (`A.Stock`) gets seeds of all seven. The potting
  bench gets a trowel, a watering can and a mortar and pestle.
- **Crew:** the new place tag `hydroponics` gets scenes and barks written in
  `design/crew/hydroponics.txt`: botanists fussing over the plomeek, a
  Klingon checking on the worms, arguments over whether homegrown tea is
  worth the tray space.

### 6.4 Tests

- **Static:** every crop prop has all five sprite tables of equal length,
  every sprite is in the pack, every seed and produce item resolves, and
  every recipe input and output resolves (`test_assets.py`).
- **The simulation:**
  - The deck builds with its trays primed.
  - A rebuild keeps a planted crop.
  - The greenhouse rule holds.
  - The worm tank breeds with food and starves without it.
  - A recipe run produces its dish.

  The sim does not have vanilla's farming system, so the farming half is
  checked by calling our hooks with a stub. The real proof is the game.

---

## 7. Phases

1. **One crop, end to end: tea to Earl Grey.** The tray, priming, the
   greenhouse rule, the tea crop and its sprites, drying on a vanilla rack
   placed by hand, and the brew recipe. This proves every unknown in §9 on
   the cheapest crop, before paying for seven sets of art.
2. **The other six crops,** their items and recipes, and the galley range.
3. **Deck 5:** the section, the furniture, the stock and the botany PADD.
4. **The worm tank** and gagh.
5. **The crew's hydroponics talk.**

---

## 8. What the research found

This is the evidence behind the design, from the game's own Lua and bytecode.

**Farming:**
- **Dig menu.** `ISFarmingMenu.canDigHereSquare` refuses z > 0 and
  non-dirt, but only in the client menu. `SFarmingSystem:plow(sq)` and
  `seed()` accept any square.
- **Crop format.** A crop is a `farming_vegetableconf.props` entry: seed,
  produce, `timeToGrow` hours per stage, water, `harvestLevel`,
  `fullGrown`, months and yield. The sow menu lists every prop
  automatically.
- **Sprites.** Growth sprites are any names, picked by stage and health
  (`getSpriteName`). The plowed state is hard-coded to vanilla's
  `vegetation_farming_01_1`: soil in the tray.
- **Indoors.** Health loses 1 every 2 hours indoors with `KillInsideCrops`
  unless the room is a greenhouse or the prop is `isHouseplant`. Cold under
  10°C hurts unless `coldHardy`.
- **Outdoors.** Our deck has no RoomDefs and may count as *outside*, which
  brings rain, winter and bad months. Hence §6.3's wrap.
- **Multiplayer.** A plant is a server global object (`gos_farming.bin`)
  that ticks every 10 minutes whether or not its chunk is loaded, and is
  synced by vanilla.
- **Worms.** The composter breeds `Base.Worm` (hard-coded), and worms in it
  never rot.
- **No planters.** No vanilla planter grows crops.

**Crafting:**
- **Recipes.** A `craftRecipe` in our own module shows in the crafting UI
  automatically. `Tags` binds a recipe to a workstation (`DryingRackHerb`,
  `Stone_Quern`, `CoffeeMachine`). `NeedToBeLearn` with `AutoLearnAny` or a
  `LearnedRecipes` item gates it.
- **Hot drinks.** Vanilla hot tea and coffee are an evolved `HotDrink` food
  heated afterwards, not fluids. The mod's own `TrekEarlGrey` and
  `TrekRaktajino` fluids are kept by a recipe that outputs the pre-filled
  mug.
- **Soups.** The evolved-soup name is built from the ingredients, so
  "Plomeek Soup" comes for free when plomeek is the only one.
- **Drying.** Drying on a rack is any craftRecipe tagged `DryingRackHerb`.
  `time` is in game-seconds; 86400 is one day.
- **Multiplayer.** Handcrafting runs on the server (`ISHandcraftAction`);
  outputs sync by themselves.

---

## 9. Open questions (the first play-test of phase 1 answers most)

1. **The galley range.** Can a runtime Starfleet sprite be a working stove,
   as the shuttle's oven is, powered by a bus? Or is the honest answer a
   vanilla oven sprite in her galley? Phase 2 decides.
2. **Drying aboard.** Vanilla drying racks are *entities* built by the
   player. Can the server place one, as the dehydrator, or do we ship a
   `dehydrate` handcraft recipe that takes a game-day of wait? Phase 1 uses
   a hand-built vanilla rack and finds out.
3. **Inside or outside.** Is `sq:isOutside()` true on her deck? The wrap
   covers either answer, but it decides whether rain reaches the trays.
4. **The heat of a mug.** Does `setItemHeat` on a fluid mug make the Earl
   Grey hot when drunk, or is "hot" only in the name?
5. **Seeds from the replicator.** Allowed? It makes the trays reachable
   without the seed locker, and replicated seeds still grow **real** food.
   Recommended yes.

---

## 10. As built (2026-09-26)

Every phase in §7 is done in one pass.

| What | Where |
|---|---|
| Crop registration | `shared/TREK/TREK_FarmCrops.lua` (it loads on clients too, for the sow menu) |
| Growth sprites | `shared/TREK/TREK_FarmSprites.lua` (GENERATED) |
| Trays, the greenhouse rule, tending, the dehydrator, the worm tank | `server/TREK/TREK_Farm.lua` |
| Items and the 21 recipes | `media/scripts/trekfarming.txt` |
| Growth stages | `tools/gen_adirondack_crops.py` → sheet `trek_adirondack_03` (224 stage tiles and the tray's soil) |
| Furniture | `tools/adirondack_objects.py`, appended to sheet `02` so every existing tile keeps its number: `hydro_tray`, `seed_locker`, `potting_bench`, `dehydrator`, `worm_tank`, `galley_range`, `arboretum_tree`, `alien_shrub`, `grow_light` |
| Icons | `tools/gen_farm_icons.py`. It crops each raw to its magenta panel first, because Gemini sometimes paints the magenta as a panel inside a bigger picture. |
| Deck 5 | `SECTIONS["hydroponics"]` and `DECKS` in `compose_adirondack.py`. The decks are ordered by deck number, never by storey, so Deck 5 stands east of Deck 4 and nothing already built moves. |
| The galley range | on Deck 2, an `IsoStove`, powered by an invisible generator on its own square and billed to her warp core (`AS.servicePowerBus`) |
| Tests | `tests/test_farming.py` (static: every recipe item and tag, every crop's items and sprites) and `farming()` in `tests/test_multiplayer.py` (the loop, in the sim) |

**The bay runs itself.** Every hour the ship does all of this to each plant
aboard her:
- waters it full;
- clears any pests and disease;
- restores any health it lost to being "indoors" or out of season.

A harvested or dead tray is cleared and primed again within the hour. The
crew only sow and harvest. The same crops planted **in the ground** in
Kentucky are ordinary vanilla crops and need ordinary care.

Sandbox *Hydroponics tend themselves* (on by default) turns the tending off.

**Decided:**
- Seeds come out of the replicator like any mod item. What grows from them
  is real food.
- Recipes are not gated: anybody can cook from scratch.

**Only the game can show:**
1. Crops standing *in* the trays at the right height (`TRAY_TOP`).
2. Vanilla's own sow, harvest and info menus on a tray square five storeys up.
3. The range cooking, with the bus powering it.
4. The drinks arriving hot (`TREKFarm_HotDrink` is named in the recipes but
   not written yet; see below).
5. A dried item keeping its count through the dehydrator.

**The brewed drinks arrive hot.** `TREKFarm_HotDrink`
(`shared/TREK/TREK_FarmRecipes.lua`) is the `OnCreate` for both brews, and it
sets the mug's item heat. Whether that heat does anything when drunk is item 4
above.
