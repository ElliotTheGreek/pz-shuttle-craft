# Hydroponics developer guide

Deck 5 of the U.S.S. Adirondack is a working farm. Seven alien and Earth crops
grow in hydroponic trays that the ship tends by itself. What they yield is
dried, ground, brewed and cooked into the species dishes the mod already had.
A tank of serpent worms breeds when it is fed, and five of them in a bowl are
gagh. Deck 2's galley has a real stove, a sink and a cupboard of cookware.

**The one design decision everything rests on: the crops are vanilla's.**
- **Crops.** All seven are vanilla crop types, and trays are primed with
  vanilla's own server `plow`. Vanilla's menus sow, water, cure and harvest
  them; its global object system grows them, saves them and syncs them in
  multiplayer.
- **Cooking.** It is vanilla crafting: `craftRecipe`s, stoves, pots, the
  mortar and pestle.

What this mod adds is only what vanilla cannot know about a starship: where
the trays are, that the ship tends them, and how to draw a crop standing in a
tray.

This guide describes the system as it is. The original plan, with its research
notes, is commit `8f885bc`.

---

## Quick verification (in game)

1. Beam to the Adirondack, then take the turbolift to Deck 5.
2. **The bay is already planted:**
   - the front row has one of each crop, ready to harvest;
   - the middle row has one of each still growing;
   - the back row is empty, showing soil.
3. **Harvest** a front-row plomeek (right-click the tray).
   - Its tray should empty to soil at once.
   - Harvest a front-row tea bush: it should stay, smaller, and grow back.
4. **Sow** a back-row tray. Take seeds from the Botany Lab's seed locker,
   then right-click the tray and choose Plowed Land, then Sow. The seedling
   should stand *in* the tray.
5. **Cook.** On Deck 2's galley:
   - fill a pot at the sink;
   - craft a Pot of Plomeek;
   - put the pot in the range and turn it on;
   - craft Serve Plomeek Soup, with bowls from the galley cupboard.

Confirmed in game on 2026-09-26: steps 2 to 5 (for step 3, the harvest
itself).

---

## Where everything lives

| File | What it is |
|---|---|
| `lua/shared/TREK/TREK_FarmCrops.lua` | The seven crops, `F.register()`, `F.onShip()` and `F.ensure()` (see engine facts). Shared, because vanilla's sow menu reads the crop table on the client. |
| `lua/shared/TREK/TREK_FarmSprites.lua` | **GENERATED.** Each crop's five sprite tables, and `TREK_FarmSoil`. |
| `lua/server/TREK/TREK_Farm.lua` | Everything else, and only on the server: priming, pre-planting, the harvest and health wrappers, tending, the dehydrator, the worm tank, the hourly pass. |
| `lua/client/TREK/TREK_FarmClient.lua` | Calls `F.ensure()` just before vanilla builds the sow menu. |
| `lua/shared/TREK/TREK_FarmRecipes.lua` | `TREKFarm_HotDrink`, the `OnCreate` both brews name. |
| `media/scripts/trekfarming.txt` | 22 items (seeds, produce, processed ingredients, the serpent worm, two stew pots) and 21 recipes. |
| `lua/shared/TREK/TREK_Adirondack.lua` | `A.Stock` / `A.stockItems`: what the seed lockers, potting benches, worm tanks and galley cupboard hold. `A.Water`: which pieces are sinks. |
| `lua/server/TREK/TREK_AdirondackServer.lua` | The galley range as an `IsoStove`, `AS.servicePowerBus`, and the deck builder's rule that leaves plants alone. |
| `Translate/EN/Farming.json` | The crop names, `Farming_<Crop>`, which vanilla's info window needs. |
| `Translate/EN/Recipes.json` | The recipe names. |
| `ItemName.json`, `Tooltip.json` | The item names and tooltips. |
| `Sandbox.json`, `sandbox-options.txt` | `TrekShuttle.HydroponicsWater`, shown as *Hydroponics tend themselves*. |

**Generators, in the order to run them after a change:**

| Tool | Makes |
|---|---|
| `tools/gen_adirondack_crops.py` | The growth sprites, rendered from each crop's mesh: sheet `trek_adirondack_03`, `TREK_FarmSprites.lua`, and `design/art/adirondack/crops_sheet.png` |
| `tools/gen_adirondack_furniture.py` | Sheet `02`, including the hydroponics furniture and `galley_cupboard` |
| `tools/gen_adirondack_pack.py` | The texture pack and tiledef, with every sheet's properties (trays, sinks, the stove, crop stages) |
| `tools/gen_adirondack_sections.py hydroponics lounge` | The Deck 5 and galley BuildingEd sections |
| `tools/compose_adirondack.py`, then `tools/gen_adirondack_lua.py` | The ship, and the layout the server builds from |
| `tools/gen_farm_icons.py` | The item icons, keyed from the Gemini raws in `design/art/food/farm/`. Each raw is first cropped to its magenta panel, because Gemini sometimes paints the magenta as a panel inside a bigger picture. |
| `tools/install_tilezed.py` | The pieces, in BuildingEd's *Starfleet – Hydroponics* and *Starfleet – Galley* groups. TileZed must be closed. |
| `tools/deploy_windows.py` | Deploy before any in-game test |

---

## The crops

| Crop (prop) | Seed → produce | Hours a stage | Yield | Kind |
|---|---|---|---|---|
| `TrekTeaBush` | `TrekTeaSeed` → `TrekTeaLeaves` | 96 | 4–7 | bush, grows back to stage 4 |
| `TrekBergamot` | `TrekBergamotSeed` → `TrekBergamot` | 120 | 2–4 | bush, grows back to stage 4 |
| `TrekKlingonCoffee` | `TrekKlingonCoffeeSeed` → `TrekKlingonCoffeeCherries` | 108 | 4–7 | bush, grows back to stage 4 |
| `TrekPlomeek` | `TrekPlomeekSeed` → `TrekPlomeek` | 72 | 2–4 | annual |
| `TrekLeolaRoot` | `TrekLeolaSeed` → `TrekLeolaRoot` | 84 | 2–4 | annual |
| `TrekAndorianTuber` | `TrekAndorianTuberSeed` → `TrekAndorianTuberRaw` | 84 | 2–3 | annual |
| `TrekHasperatPepper` | `TrekHasperatSeed` → `TrekHasperatPeppers` | 72 | 3–6 | annual |

Settings every crop shares:
- **Stages.** Eight, as vanilla's vegetables have. Stage 5 is ready to
  harvest and stage 6 is fully grown with seed. Past 6, the crop rots.
- **No seasons.** `sowMonth` is every month; there are no bad, risk or best
  months.
- **No weather or pests.** `coldHardy` and `isHouseplant`, and proof against
  aphids, flies and slugs.

Timings scale with vanilla's sandbox *Farming speed*, like any crop.

**Seeds** come from:
- a fully grown plant, at harvest;
- the `TrekSeeds<Crop>` recipes (produce and a knife);
- the seed lockers;
- the replicator, like any mod item. What grows from a replicated seed is
  real food.

**Real food matters.** Homegrown produce carries no replicated mark.
Klingons and *Real Food Only* characters are penalised for replicated food
(TRAITS.md), and every dish is some species' comfort food
(`C.SpeciesFood`).

---

## The trays

`hydro_tray` is a piece of furniture: 21 of them, in three rows of seven on
Deck 5.

- **Priming.** A tray is primed by the server calling
  `SFarmingSystem.instance:plow(sq)`, which makes a vanilla "Plowed Land"
  plot on the tray's square. It happens when the deck is built, and in the
  hourly pass for any tray that has nothing on it.
- **Sowing and harvest** are vanilla's own menus on that plot.
- **After harvest:**
  - An annual's tray is cleared and primed *at once*, by `F.wrapHarvest`
    around `SFarmingSystem.harvest`.
  - A bush is left to grow back (`growBack = 4`).
- **Dead or rotten** plants are cleared and the tray primed in the next
  hourly pass. `F.primeTray` treats harvested, destroyed, dead and rotten
  alike.
- **Starting planted.** `F.stockBay`, once per world (`farmStocked` in the
  Adirondack's state), sows `F.StartRows`:
  - the front row at stage 5;
  - the middle row at stages 2–4;
  - using vanilla's own `seed()` and `growPlant()`.

  It sows only trays still waiting, so a tray a player has planted is never
  touched.
- **Not movable.** Trays cannot be disassembled or scrapped. Taking one apart
  would take its crop with it.

### How a crop is drawn in a tray

`tools/gen_adirondack_crops.py` renders each crop's TRELLIS mesh of the mature
plant (its concept and mesh are in the ledger, `tools/adirondack_jobs.py`).
Every tile is 128×256 and the plant stands on `TRAY_TOP` (0.47), the height of
the tray's growing medium.

| Table | What it is |
|---|---|
| `sprite` | the mesh at eight scales, `STAGE_SCALE` (0.16 → 1.0), with stages 7 and 8 lightly tinted: seeding, then going over |
| `unhealthy`, `dying`, `dead` | the same renders, tinted yellow, brown and grey |
| `trampled` | the tray's bare soil, eight times. Vanilla draws harvested and destroyed plants from this table. |
| `_soil` / `TREK_FarmSoil` | a disc of dark growing medium at the top of the tray |

The crop tiles carry only `BlocksPlacement`:
- **never `attachedFloor`,** or they would draw at floor level beneath the
  tray;
- **never the vegetation flags,** which vanilla reads as weeds.

---

## The bay runs itself

Every game hour (`F.hourly`, on the server):

| Step | What it does |
|---|---|
| `F.ensure()` | puts the crops back if they were wiped (see engine facts) |
| `F.wrapHealth()`, `F.wrapHarvest()` | installs the two wrappers, once |
| `F.tendAll()` | every live plant **aboard her** is watered full and has its pests and disease cleared. Sandbox *Hydroponics tend themselves* turns it off. |
| `F.primeDeck(k)`, `F.stockBay(k)` | trays primed, and the bay stocked once |
| `F.serviceDehydrators(k)`, `F.serviceWormTanks(k)` | see the next section |

**The greenhouse rule** (`F.wrapHealth`) is a wrapper around vanilla's
`SFarmingSystem.changeHealth`. A plant aboard her keeps any health that pass
would take. The deck has no rooms, so vanilla would otherwise see it as
indoors (`KillInsideCrops`) or as outdoors in winter.

"Aboard her" means `F.onShip(plant)`, which is `A.locate` on the plant's
square. **The same crops planted in the ground below get none of this.**
There they are ordinary vanilla crops and need watering, weeding and curing.

---

## The dehydrator and the worm tank

Both are server hooks on the containers of one piece of furniture, on every
built deck. Neither is something vanilla does.

**The dehydrator** (`F.Dry`, `F.DryHours = 12`):
- An item of a type in `F.Dry` gains one hour of drying for each game hour
  it spends inside.
- At 12 hours it is replaced by its dried form:
  - tea leaves become dried tea;
  - coffee cherries become coffee beans;
  - hasperat peppers become dried hasperat.
- Vanilla herb drying racks dry the same three, through the
  `TrekDry*` recipes tagged `DryingRackHerb`.

**The worm tank** (`F.WormCap = 20`, `F.WormBreedHours = 6`,
`F.WormStarveHours = 24`):
- **Feeding.** Any food item in the tank is feed, found by
  `instanceof(it, "Food")` or `IsFood()`.
- **Breeding.** With at least two worms and some food, every 6 hours one
  food item is eaten and one `TrekSerpentWorm` is born, up to 20.
- **Starving.** With no food for 24 hours, one worm dies. A tank never goes
  below two, so it can always recover.
- **Never rotting.** Worms in a tank have their age reset every hour, as
  vanilla's composter does for its worms.
- **Starting stock.** Each tank starts with three worms (`A.Stock`).

---

## Recipes (`media/scripts/trekfarming.txt`)

None of them has to be learned: anybody can cook from scratch. All of them
appear in the crafting window automatically.

| Dish | How it is made |
|---|---|
| **Earl Grey** (`TrekEarlGreyCup`) | Dry the tea leaves (dehydrator or herb rack). Zest a bergamot (`TrekZestBergamot`, with a knife; makes 3). **`TrekBrewEarlGrey`**: a mug holding 0.2 of water, the dried tea and a zest make the mod's Earl Grey mug. |
| **Raktajino** (`TrekRaktajinoMug`) | Dry the coffee cherries into beans. Roast the beans in an oven (they are cookable). Grind them with a mortar and pestle (`TrekGrindKlingonCoffee`, three *cooked* beans). **`TrekBrewRaktajino`**: a mug holding water, and the grounds. |
| **Plomeek soup** (`TrekPlomeekSoup`) | **`TrekMakePlomeekPot`**: a pot holding 1.0 of water, and three plomeek. Cook it in a stove. **`TrekServePlomeek`**: the cooked pot and three bowls make three soups and give the pot back. |
| **Leola root stew** (`TrekLeolaStew`) | The same, with `TrekMakeLeolaStewPot` and `TrekServeLeolaStew`. |
| **Hasperat** (`TrekHasperat`) | **`TrekMakeHasperat`**: a tortilla and two peppers, fresh or dried. |
| **Roasted Andorian tuber** (`TrekAndorianTuber`) | Cook the raw tuber in an oven. Then **`TrekPlateAndorianTuber`**. |
| **Gagh** (`TrekGagh`) | **`TrekServeGagh`**: five serpent worms and a bowl. |

**How the recipes are written:**
- **Fixed recipes, not evolved soups.** The pots and serve steps are
  `craftRecipe`s rather than vanilla's evolved soups for two reasons. An
  evolved soup renames itself from its ingredients ("Vegetables Soup" once
  anything else goes in). And it would not produce the mod's own dish items,
  which are what `C.SpeciesFood` recognises.
  - Plomeek and leola root still carry `EvolvedRecipe`, so they work in
    vanilla soups and stews too.
  - Dried tea carries `HotDrink`.
- **Hot drinks.** Both brews name `OnCreate = TREKFarm_HotDrink`. It sets the
  made mug's item heat to 1.8, and on a server it sends `sendItemStats`.
  - An `OnCreate` is `function(craftRecipeData, character)`; the made items
    come from `craftRecipeData:getAllCreatedItems()`.
  - It runs where the recipe is performed (the server, on a server), so it
    lives in `shared/`.
- **Syntax.**
  - Tags take vanilla's `base:` prefix: `tags[base:sharpknife]`,
    `tags[base:coffeemaker]` (mugs), `tags[base:mortarpestle]`.
  - A fluid input is a `-fluid N categories[Water] mode:mixture` line
    directly after the item that holds it.
  - A cooked input needs `flags[IsCookedFoodItem]`.

---

## The galley (Deck 2)

| Piece | What it is |
|---|---|
| `galley_range` | Placed as an `IsoStove` (`make()` in the deck builder), with a vanilla oven's tile properties. **A pot goes *in* it and cooks while it is on;** vanilla stoves have no separate hob. It needs power. |
| The power bus | `AS.servicePowerBus(k)` puts an invisible `IsoGenerator` **on the range's own square**. It is refuelled every hour, the fuel billed to her warp core (`Power.using("adk", ...)`), and switched off if she goes dark. |
| `galley_sink`, and every `wash_basin` | Real sinks. Their tiles carry vanilla's `waterPiped` / `waterAmount` properties, which make vanilla offer fill, wash and drink. Behind that is the water store the builder gives every `A.Water` piece, topped up by `refillWater`. |
| `galley_cupboard` | A piece of its own so it can be stocked separately; its mesh is a copy of `galley_counter.glb`. It holds 2 pots, a saucepan, a pan, a roasting pan, a baking tray, a kettle, 6 bowls, 4 mugs, a kitchen knife, a mortar and pestle, a spoon, fork, ladle and spatula, an oven mitt and 4 tortillas. |

Deck 5's **Botany Lab** has:
- two seed lockers, 5 seeds of every crop in each;
- a potting bench;
- the dehydrator, a replicator, a desk and a science display.

The **bay** has:
- a second potting bench;
- a wash basin;
- grow lights;
- an arboretum corner, with a tree, shrubs and a chair.

Each potting bench holds a hand shovel, a watering can, a mortar and pestle,
a pot, a bowl and a kitchen knife.

The **Serpent Tank Room** has two worm tanks.

---

## Engine facts this depends on

Every one of these cost a play-test, or was read out of vanilla's own code.
Check this list before changing anything.

1. **Vanilla wipes the crop table when its farming config loads.**
   - `farming_vegetableconf.lua` resets `props` and the sprite tables, and it
     can load after our registration. The first play-test's sow menu was
     empty for exactly this reason.
   - Hence `F.ensure()`: idempotent, and called at file load, `OnGameBoot`,
     `OnGameStart`, `OnInitGlobalModData`, `OnServerStarted`, every hour,
     and just before `ISFarmingMenu.doSeedMenu`.
   - **Never register the crops once and trust it.**
2. **The dig menu refuses our deck; the server's `plow` does not.**
   `ISFarmingMenu.canDigHereSquare` wants z = 0 and natural dirt, but it is a
   client menu check. `SFarmingSystem:plow(sq)` and `seed()` work on any
   square, which is why trays are primed by the server.
3. **A plowed plot's sprite is hard-coded.**
   - `farming_vegetableconf.getSpriteName` answers `vegetation_farming_01_1`
     for a plowed plot. Vanilla resets every plant's sprite from it on its
     checks, so setting a sprite once is undone within minutes.
   - `F.ensure()` wraps `getSpriteName` so that a plowed plot aboard her
     answers `TREK_FarmSoil`.
4. **Vanilla draws a harvested plant from its `trampled` table.** Ours is
   bare soil. A tinted whole plant there read as a harvest that took nothing.
5. **The deck builder strips untagged objects from every deck square.**
   - A vanilla plant is untagged. `AS.buildDeck` skips any object whose mod
     data has `typeOfSeed` or `nbOfGrow`, and any `IsoGenerator`.
   - **Anything new that vanilla places on a deck needs the same exemption,**
     or the next rebuild deletes it.
6. **Indoor and outdoor are unanswerable on a runtime deck.** It has no
   RoomDefs. The greenhouse rule is what makes the question moot, so do not
   remove it because the crops are `isHouseplant`.
7. **Every sprite table is required.** `MOFarming` indexes all five tables
   for every crop and throws on a missing one.
8. **Sheet `02` is append-only.**
   - A built deck names its tiles by index, so a new piece goes at the *end*
     of `OBJECTS` in `tools/adirondack_objects.py`.
   - After regenerating, check that no existing piece's tile index has moved.
   - Crops are `kind = "crop"` in the manifest and are skipped there; their
     sheet is `03`.
9. **Decks are ordered by number, never by storey.** Sorting by storey put
   Deck 5 first, which would have moved every deck already built in a save
   (`gen_adirondack_lua.py`).
10. **A sink needs vanilla's properties on its tile.** A water store alone
    gives no fill or wash options; `waterPiped` is what vanilla's menus look
    for.

---

## Adding a crop

1. **Concept and mesh.**
   - A Gemini concept of the mature plant, alone, on a mound of dark growing
     medium, with no pot.
   - A TRELLIS mesh from it (seed 1701).
   - Add `crop("crop_<name>", ...)` to the end of
     `tools/adirondack_objects.py`, and record both in the ledger
     (`tools/adirondack_jobs.py set ...`, then `fetch`).
2. **Sprites.** Add a row to `CROPS` in `tools/gen_adirondack_crops.py` (the
   prop name, the mesh, the mature height and the spread), then run it.
3. **Items.** In `trekfarming.txt`, add a seed (`Tags = base:isseed`), the
   produce, and a `TrekSeeds<Crop>` recipe. Then:
   - names in `ItemName.json`;
   - tooltips in `Tooltip.json`;
   - icons through `tools/gen_farm_icons.py`.
4. **Registration.** Add the crop to `F.Crops` in `TREK_FarmCrops.lua`, and
   add `Farming_<Prop>` to `Farming.json`.
5. **Stock.** Add the seed to the `seeds` list in `A.stockItems`. To have it
   pre-planted, add it to `F.StartRows` (a row holds seven).
6. **Build.** Run `tests/test_farming.py` and `tests/test_multiplayer.py`,
   then `tools/gen_adirondack_pack.py`, then deploy.

## Adding a recipe

1. Write a `craftRecipe` in `trekfarming.txt`: module `TrekShuttle`, with
   full `Base.` / `TrekShuttle.` names and `base:` tags.
2. Give it a name in `Recipes.json`.
3. If it names an `OnCreate`, define that global function in `lua/shared/`.
4. Run `tests/test_farming.py`. It fails on any unknown item or tag, a
   missing name, or an `OnCreate` that no Lua file defines.

---

## Symptom map

| What you see | Why, and where to look |
|---|---|
| **Sow submenu empty** | The crop table was wiped after we registered (engine fact 1). Is `F.ensure()` still hooked, and does `TREK_FarmClient` still wrap `doSeedMenu`? |
| **Brown furrows at the foot of a tray** | Vanilla's plowed sprite (fact 3). Is the `getSpriteName` wrapper installed, and does `F.onShip` find the plant? |
| **A plant still standing after harvest** | A bush grows back; that is by design. If it is an annual: is `F.wrapHarvest` installed, and does the `trampled` table point at the soil? |
| **Crops gone after a deck rebuild** | The builder's plant exemption (fact 5) |
| **Crops losing health, or dying, aboard her** | The greenhouse rule (`F.wrapHealth`) |
| **Crops drying out aboard her** | *Hydroponics tend themselves* is off, or `F.tendAll` is not reaching them (`F.onShip`) |
| **A crop floats above, or sinks into, its tray** | `TRAY_TOP` in `gen_adirondack_crops.py`. Change it, then re-render. |
| **The range will not heat** | The power bus: an `IsoGenerator` on the range's square, activated, and her store not dark. Is the range an `IsoStove`? A refit replaces one that is not. |
| **No fill or wash at a sink** | Its tile needs `waterPiped` (fact 10; `test_farming.py` checks), and its object needs a water store (`A.Water`) |
| **The dehydrator does nothing** | Only the three types in `F.Dry` dry, and only on a built deck, in the hourly pass |
| **Worms not breeding** | They need at least two worms and some food, in the tank, for six game hours |
| **Empty seed locker in an old world** | Containers are stocked once, when they are built. A world whose deck was built before a stock change keeps what it had. |

---

## Tests

**`tests/test_farming.py`** (static):
- every item and tag a recipe names exists;
- every recipe has a name, and every `OnCreate` is defined;
- every crop names real items, has its `Farming.json` name, and has five
  sprite tables of eight whose pictures are in the pack;
- the sinks carry `waterPiped`.

**`farming()` in `tests/test_multiplayer.py`** (the simulation):
- the crops are registered, and put back after vanilla wipes the table;
- the bay starts 7 ready, 7 growing and 7 empty;
- an empty tray shows soil while a plot in the ground shows furrows;
- the lockers, benches and tanks are stocked;
- tending, and the greenhouse rule;
- a crop in the ground below is left alone;
- a crop survives a rebuild;
- an annual's tray re-primes at harvest while a bush grows back;
- the dehydrator dries, and the tank breeds and starves;
- the range is an `IsoStove` with a bus, and the cupboard holds cookware.

The simulation stands in for vanilla farming with a small stub
(`tests/pz_sim.lua`). It proves our hooks, not vanilla's growth, which only
the game shows.

**Still unconfirmed in game:**
1. The height of a growing crop in its tray (`TRAY_TOP`).
2. The brewed drinks' heat: does `setItemHeat` on a fluid mug do anything when
   it is drunk?
3. The dehydrator, and whether a dried stack keeps its count.
4. The worm tank breeding.
5. The galley sink offering fill and wash.
