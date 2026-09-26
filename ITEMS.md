# ITEMS.md — everything the mod has made

An inventory of what the mod adds to the world: the items you carry, the
furniture that stands on the decks, and what is in each container of the
shuttle and the U.S.S. Adirondack when she sails.

Where things are defined:

| What | Where |
|---|---|
| Item scripts | `TrekShuttle/42/media/scripts/trekshuttle.txt`, `trekweapons.txt` |
| Item names | `media/lua/shared/Translate/EN/ItemName.json` |
| Loot lists | `C.Loot.*` in `TREK_Config.lua` |
| Shuttle cabin | `TREK_InteriorLayout.lua` (containers), `TREK_Build.lua` (`SPECIALS`) |
| Adirondack | `A.Stock` / `A.Water` in `TREK_Adirondack.lua`; furniture in `design/tiles/trek_adirondack_02.json` |

Every item id below is `TrekShuttle.<id>`.

---

## 1. Items you carry

### Weapons

| Item | Id | Notes |
|---|---|---|
| Phaser | `TrekPhaser` | A ranged beam weapon that also cuts down trees and cuts through doors. Four are issued in the shuttle's armoury. |
| Bat'leth | `TrekBatleth` | Klingon blade, two-handed |
| Mek'leth | `TrekMekleth` | Klingon short blade |
| Lirpa | `TrekLirpa` | Vulcan polearm |
| Ushaan-tor | `TrekUshaanTor` | Andorian ice-miner's blade |

### Medical and tools

| Item | Id | Notes |
|---|---|---|
| Hypospray | `TrekHypospray` | Treats what a hypo can |
| Dermal Regenerator | `TrekDermalRegen` | Closes skin; refuses a wound with glass in it |
| Medical Tricorder | `TrekMedTricorder` | Diagnoses |
| Tricorder | `TrekTricorder` | Scanning tool |
| PADD | `TrekPADD` | Personal: holds its own library and comms |

### Food: dishes

Each species dish comforts its own species and unsettles anybody else's
(`C.SpeciesFood`). A Vulcan will not eat meat or a Klingon dish. A Klingon, or
anybody with *Real Food Only*, is unhappy with replicated food.

| Item | Id | Species |
|---|---|---|
| Starfleet Ration Pack | `TrekRationPack` | — |
| Gagh | `TrekGagh` | Klingon |
| Rokeg Blood Pie | `TrekRokegPie` | Klingon |
| Plomeek Soup | `TrekPlomeekSoup` | Vulcan |
| Andorian Tuber Root | `TrekAndorianTuber` | Andorian |
| Oskoid | `TrekOskoid` | Betazoid |
| Jumja Stick | `TrekJumjaStick` | Bajoran |
| Hasperat | `TrekHasperat` | Bajoran |
| Leola Root Stew | `TrekLeolaStew` | Talaxian |
| Steamed Chadre'kab | `TrekChadrekab` | Talaxian |
| Wing-Slug Roll | `TrekWingSlugRoll` | Orion |

### Food: drinks

| Item | Id |
|---|---|
| Raktajino | `TrekRaktajinoMug` |
| Earl Grey Tea | `TrekEarlGreyCup` |
| Romulan Ale | `TrekRomulanAle` |
| Bloodwine | `TrekBloodwine` |
| Andorian Ale | `TrekAndorianAle` |
| Balso Tonic | `TrekBalsoTonic` |
| Nutrient Suspension | `TrekNutrientSuspension` (on the food list, not the bar's) |

### Clothing

| Item | Id |
|---|---|
| Starfleet Uniform (Command / Operations / Sciences) | `TrekUniformDutyCommand`, `…Operations`, `…Science` |
| Starfleet Dress Uniform (Command / Operations / Sciences) | `TrekUniformDressCommand`, `…Operations`, `…Science` |

Together these six are `C.UniformIssue`.

**Species looks** are worn items, chosen at character creation, and are not
found anywhere in the world:
- Trill Spots, Bajoran Nose Ridges, Betazoid Eyes, Klingon Brow Ridges,
  Talaxian Mottling and Borg Ocular Implant come in male and female versions (`TrekLook_<species>_M/F`).
- Vulcan Ears (`TrekLook_vulcanears`) and Andorian Antennae (`TrekLook_antennae`) have one version each.

### Story, media and materials

| Item | Id | Notes |
|---|---|---|
| Dilithium Crystal | `TrekDilithium` | Powers a warp core. Found in the wild (sandbox `WildDilithium`). **Cannot be replicated.** |
| Blank Tape | `TrekTape` | One item type. The recording on it is what differs. |
| Holo Fragment 1–6 | `TrekFragment1`…`6` | The story fragments; found at sensor contacts |

**The tapes the shuttle's shelf is stocked with** (`TREK_TapeIds`):
- Ten Forward Talent Night
- Dear Grandpa Tuvix
- Personal Log: Entries One to Six
- The Cardassian Prisoner
- Board of Examiners: oral re-examination
- Deposition: in the matter of a quantity of latinum
- Determination in the matter of Rana Four

Six more recordings exist and are not on the shelf: *Unlabelled recording* and
*Fragment one* to *six*. They come with the story.

### Items nobody holds

These are items only because the engine needs them to be. Each is a world
model standing on the deck, or something handed to the engine and thrown
away. The replicator refuses most of them (`C.ReplicatorBlocked`).

| Item | Id | What it is |
|---|---|---|
| Shuttlecraft | `TrekShuttleHull` | The hull model |
| Helm Console | `TrekHelmConsole` | The helm |
| Replicator | `TrekReplicator` | The shuttle's replicator alcove |
| Warp Core | `TrekWarpCore` | The shuttle's core |
| Emergency Medical Hologram | `TrekEMH` | The Doctor, when he is up |
| EMH Projector Station | `TrekEMHStation` | His emitter in the shuttle |
| Shuttle Power Bus | `TrekPowerBus` | The galley's generator, kept out of sight |
| Photon Torpedo | `TrekTorpedo` | The warhead an explosion is copied from. Torpedoes are a cooldown, not ammunition. |
| Downed Starfleet Ensign | `TrekEnsign{M,F}{Command,Operations,Science}` | The ensign, as a body in the world |

---

## 2. Furniture in the world

### The shuttle's cabin (4 × 6 squares)

Built from vanilla sprites, plus the mod's own world models:

- **Bow:** monitor wall (3 consoles), television on a low table, the tape shelf, and a crew seat.
- **Port (galley):** fridge, oven, two counters, sink, microwave, and the **replicator** (world model).
- **Starboard:** three Starfleet lockers (armoury, provisions, medical), then the biobed.
- **Midships:** the **warp core** (world model) and the **EMH projector station**.
- **Aft:** the transporter pad.

### The Adirondack: 50 original pieces (`trek_adirondack_02`)

Each piece is modelled and rendered into tiles, in every facing it needs.
"Deck" counts are whole pieces as placed.

| Piece | Does | D1 Bridge | D2 Lounge & Habitat | D3 Transporter & Sickbay | D4 Engineering |
|---|---|---|---|---|---|
| captain_chair | seat | 1 | | | |
| bridge_chair | seat | 4 | | | |
| helm_console | — | 2 | | | |
| science_station | — | 4 | | | |
| science_display | — | 2 | | | |
| tactical_rail | — | 1 | | | |
| railing | — | 4 | | | 4 |
| ready_room_desk | container (desk) | 1 | | | |
| desk | container (desk) | | 4 | 1 | |
| desk_chair | seat | 1 | 4 | 1 | |
| lounge_chair | seat | 2 | 12 | | |
| lounge_table | table | | 6 | | |
| bar_straight | container (counter) | | 3 | | |
| bar_corner | container (counter) | | | | |
| bar_stool | seat | | 6 | | |
| bottle_shelf | container (shelves) | | 2 | | |
| galley_counter | container (counter) | | 4 | | |
| galley_sink | counter + **running water** | | 1 | | |
| stasis_unit | container (fridge) | | 3 | | |
| replicator | **working replicator** | 1 | 5 | | |
| bed | bed | | 2 | | |
| bed_double | bed | | 2 | | |
| bunk | bed | | 2 | | |
| nightstand | container (side table) | | 6 | | |
| wardrobe | container (wardrobe) | | 6 | | |
| display_shelf | container (shelves) | 1 | 3 | 1 | |
| sofa | seat | | 1 | | |
| armchair | seat | | 3 | 1 | |
| coffee_table | table | | 3 | | |
| sonic_shower | — | | 2 | | |
| toilet | — | | 2 | | |
| wash_basin | **running water** | | 2 | | |
| transporter_pad | the arrival pad | | | 1 | |
| transporter_console | — | | | 1 | |
| biobed | bed | | | 4 | |
| surgical_bed | — | | | 1 | |
| medical_cabinet | container (medicine) | | | 5 | |
| medical_cart | container (medicine) | | | 3 | |
| emh_station | **the Doctor, always on** | | | 1 | |
| warp_core | **her core: load / take crystals** | | | | 1 |
| master_systems | — | | | | 1 |
| engineering_console | — | | | | 7 |
| jefferies_hatch | — | | | | 2 |
| cargo_crate | container (crate) | | 1 | 1 | 5 |
| antigrav_cart | container (crate) | | | | 1 |
| turbolift_panel | wall panel | 3 | 3 | 3 | 2 |
| wall_sconce | wall light (look only) | 4 | 7 | 7 | 5 |
| plant | — | 2 | 6 | 3 | |
| painting_ship / painting_nebula | wall art | 1 | 3 | 1 | |
| plaque | wall art | | | 1 | |

Notes on the pieces:
- **Seats and beds:** the position of every seat and bed tile is in
  `common/media/seating.txt`, copied from the vanilla piece it stands in for.
  To sleep *in* a bed, Rest on it first and then Sleep.
- **The structure** is the other sheet, `trek_adirondack_01`: bulkheads,
  viewports, carpet and deck plate, sliding doors (which open by themselves)
  and LCARS wall panels.
- `bar_corner` is modelled but not placed anywhere yet.

---

## 3. What is in the containers

How much goes in:
- **A loot list fill** puts items from a `C.Loot` list into the container
  until it is `C.FillFraction` (55%) full by weight, up to `C.FillItemCap`
  (48) items. The list carries on from one container to the next, so
  neighbouring lockers don't all hold the same handful.
- **A guarantee** puts in so many of each named item, and the build reads the
  container back and logs anything that didn't fit.
- **Stocked once.** Containers are filled when they are built. What the crew
  eats stays eaten, and nothing restocks by itself.

The loot lists:

| List | Items |
|---|---|
| `medical` | Hypospray, Dermal Regenerator, Medical Tricorder, Tricorder |
| `food` | the 11 dishes and 7 drinks above |
| `drinks` | Raktajino, Earl Grey, Romulan Ale, Bloodwine, Andorian Ale, Balso Tonic |
| `weapons` | Bat'leth, Mek'leth, Lirpa, Ushaan-tor |

### The shuttle

| Container | Where | Holds |
|---|---|---|
| **Armoury** locker | starboard, bow | 4 Phasers, the 6 uniforms (1 each), 2 PADDs, then the `weapons` list filled to 8 blades |
| **Provisions** locker | starboard | `food` list, filled to 27 items |
| **Medical** locker | starboard | 1 of each medical instrument, then the `medical` list, to 8 items |
| Tape shelf | bow | the 12 recordings above, one tape each |
| Fridge, oven, 2 counters, microwave | galley | empty: the crew's own |
| Warp core | midships | not a container: **3 spare dilithium crystals** (`C.DilithiumIssue`) as ship state, plus the one burning |
| Galley sink | galley | running water, kept topped up |

### The U.S.S. Adirondack

By piece (`A.Stock`). A two-square piece is two containers, and each one is
stocked.

| Piece | Where | Holds |
|---|---|---|
| medical_cabinet ×5, medical_cart ×3 | Sickbay, D3 | `medical` list |
| galley_counter ×4, stasis_unit ×3 | Galley, D2 | `food` list |
| bar_straight ×3, bottle_shelf ×2 | Lounge, D2 | `drinks` list |
| wardrobe ×6 | Quarters, D2 | the 6 uniforms, 1 each |
| desk ×5, ready_room_desk | Quarters D2, CMO's office D3, Ready Room D1 | 1 PADD and 1 Tricorder |
| display_shelf ×5 | Bridge, Quarters, Sickbay office | `weapons` list: the Klingon, Vulcan and Andorian blades on display |
| cargo_crate ×7 | Engineering D4, plus one each on D2 and D3 | 2 Phasers and 2 Tricorders |
| antigrav_cart | Engineering, D4 | 2 Dilithium Crystals |
| nightstand ×6 | Quarters | empty: the crew's own |
| **Her warp core** | Engineering, D4 | not a container: **50 dilithium crystals** in her own store (`s.adk`), plus a full reserve |
| galley_sink, wash_basin ×2 | Galley, quarters' baths | running water, kept topped up |

Stocking rules:
- **Power:** her replicators, core and EMH station run on her own store. The
  shuttle's power is never touched by anything done aboard her.
- **Updates:** when the layout changes, a deck is refitted in place. A
  container that was never stocked and is still empty gets its stock, and one
  somebody has put something in is left alone.

---

## 4. Other ways items come into the world

| Source | What you get |
|---|---|
| **Replicator** (the shuttle's, or any of the Adirondack's) | Anything the ship has a pattern for, paid in energy. Every mod item is a pattern from the start; scanning adds vanilla ones. The blocked list includes dilithium, the torpedo warhead, the hull, the helm and the power bus. |
| **The wild** | Dilithium Crystals lying in the world (sandbox `WildDilithium`: Plentiful, Scarce or Off) |
| **Sensor contacts** | The six Holo Fragments, found where a probe's contact leads |
| **Character creation** | Species looks, worn from the start |
