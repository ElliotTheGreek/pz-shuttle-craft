# The Shuttlecraft on a server

For whoever runs a server with the **Shuttlecraft** mod: what to install,
every setting and what it really does, how rare dilithium is and what
everything costs, switching whole parts of the mod off (the shuttle, the
ship in orbit, aliens, any weapon), who gets a shuttle of their own, who may board the ship in
orbit, which species, traits and professions your players may pick, how to rename things and replace the story with your own,
and the languages the mod speaks. `README.md` is what a player gets; this is
what a host gets.

Everything here is in the mod itself (Workshop **3801178990**, Mod ID
**`TrekShuttle`**).

**What has been played and what has not.** Everything in this guide passes
the mod's simulated server with two and three clients
(`tests/test_multiplayer.py`, sections `rules`, `rules_multiplayer`, `fleet`
and `fleet_off`), with every rule checked from both ends. None of the
settings added in 1.21.0 has been played on a real server yet, and the
balance and content pages (sections `balance` and `content`) have not been
played at all. `ROADMAP.md`
section 1 says which of the mod's systems have been.

---

## Installing

| | |
|---|---|
| Workshop ID | `3801178990` |
| Mod ID | `TrekShuttle` |
| Game | build 42 (written against 42.20.4) |
| Map | `TrekShuttle`, listed **before** the base map |

```ini
Mods=TrekShuttle
WorkshopItems=3801178990
Map=TrekShuttle;Muldraugh, KY
```

Every player needs the mod. The `TrekShuttle` map is a block of empty cells
far off the edge of Kentucky: the space round the shuttle's cabin, the ship
in orbit and the berths of any personal shuttles. Without it the mod still
works, the server's log says `the 'TrekShuttle' map is not loaded`, and the
view out of every cabin is a wood with zombies in it. Single player and the
in-game Host add it by themselves.

**Adding it to a running world is fine.** Nothing is built ahead of time: a
cabin is built the first time somebody stands in it. A world that never had
the mod uses the defaults below for every setting.

**The server decides everything.** The ships, their cabins and stores, power,
who may fly, land, beam and board, and every rule on this page are decided
and saved on the server. A client only ever asks (`MULTIPLAYER.md`).

**The speed anti-cheat.** Every beam, the hatch and the lifts move a
character a long way at once, and a server whose `AntiCheatSpeed` kicks or
bans counts each as two or three of the four strikes that kick. By default
the mod sets that check to *log* while the server runs (it does not touch
your `.ini`); see `SpeedCheck` below. Admins are never checked, so test with
an ordinary account.

---

## The settings

The sandbox has four pages, **Shuttlecraft**, **Shuttlecraft: balance**,
**Shuttlecraft: content** and **Shuttlecraft: roleplay**.
In a server's `<name>_SandboxVars.lua` they are one table, `TrekShuttle`. The
numbers are what goes in that file; the first column of each table is the
name to use. Every one of them can also be changed from the admin panel's
sandbox options while the server runs, and unless a table says otherwise the
change takes effect at once.

```lua
TrekShuttle = {
    -- Shuttlecraft
    Access = 1, TransporterLimit = 1, SpeedCheck = 1, TorpedoFire = 1,
    Replicator = 1, EMH = 1, FlightHeight = 4, CommsFirstDay = 4,
    StartState = 3, PhaserCutting = 1, HydroponicsWater = 1,
    Borg = 1, CaptainTruth = 2, AdirondackAccess = 1, AdirondackRescues = 3,
    Raids = 3, RaidSize = 2,
    BeamUp = true, Flight = true, ShipWeapons = 1, Shields = true,
    DistressCalls = true, Installations = true,
    -- Shuttlecraft: balance
    LootDilithiumMin = 1, LootDilithiumMax = 5, WildDilithium = 4,
    ProbeFind = 30, RaidCrystal = 10, StartCrystals = 1,
    PowerUse = 1, CostReplicator = 100, CostTransporter = 100, CostFlight = 100,
    CostShields = 100, CostWeapons = 100, CostMedical = 100, CostSystems = 100,
    CureCrystals = 1, CureHours = 12,
    -- Shuttlecraft: content
    Shuttles = true, Adirondack = true, FieldStation = true, Aliens = true,
    ItemLoot = 3,
    ItemBatleth = true, ItemMekleth = true, ItemLirpa = true, ItemUshaanTor = true,
    ItemPhaser = true, ItemPhaserRifle = true, ItemKlingonDisruptor = true,
    ItemKlingonRifle = true, ItemRomulanDisruptor = true, ItemPolaronRifle = true,
    ItemCardassianPhaser = true, ItemSentry = true,
    ItemsMedical = true, ItemsInstruments = true, ItemsUniforms = true,
    ItemsFieldKit = true, ItemsFood = true, ItemsDrinks = true,
    ItemsContraband = true, ItemsFarming = true, ItemsKits = true,
    -- Shuttlecraft: roleplay
    AccessUsers = "", PersonalShuttles = 1, PersonalShuttleUsers = "",
    AdirondackUsers = "", AdirondackName = "Adirondack",
    SpeciesHuman = true, SpeciesVulcan = true, SpeciesKlingon = true,
    SpeciesAndorian = true, SpeciesBetazoid = true, SpeciesTrill = true,
    SpeciesBajoran = true, SpeciesTalaxian = true, SpeciesOrion = true,
    SpeciesAndroid = true, SpeciesExBorg = true,
    TraitTransporterPhobia = true, TraitRealFoodOnly = true, TraitSpacesick = true,
    TraitStarfleetAcademy = true, TraitHoloHistorian = true, TraitTurboliftPhobia = true,
    ProfessionCommand = true, ProfessionHelm = true, ProfessionEngineer = true,
    ProfessionSecurity = true, ProfessionMedical = true, ProfessionScience = true,
    ProfessionSurvey = true,
},
```

**A setting you leave out is the mod as designed**, never a feature switched
off. A list of names is usernames separated by semicolons (`alice;bob`);
commas work too, and capitals and spaces round a name do not matter.

### Who has a shuttle

| Setting | Values | Default | What it does |
|---|---|---|---|
| `Access` *Who may use the shuttle* | 1 Everyone, 2 Owner and crew, 3 Listed players | 1 | The **shared** shuttle. *Owner and crew*: the first player to use it owns it, and the owner or an admin adds crew aboard (*Shuttlecraft ▸ Crew*). *Listed players*: only the names in `AccessUsers`. Anyone may always beam down or step out. |
| `AccessUsers` *Shuttle users* | names | empty | Who may use the shared shuttle when `Access = 3`. Empty with `Access = 3` is nobody but admins. |
| `PersonalShuttles` *Personal shuttles* | 1 None, 2 Every player, 3 Listed players | 1 | Gives players a shuttle **each**, with its own cabin, stores and power. See *A shuttle each* below. |
| `PersonalShuttleUsers` *Personal shuttle users* | names | empty | Who has one when `PersonalShuttles = 3`. |

### The ship in orbit

| Setting | Values | Default | What it does |
|---|---|---|---|
| `AdirondackAccess` *Adirondack access* | 1 Earned, 2 Open from the start, 3 Rescues only, 4 Closed | 1 | *Earned*: her crew brought home, a transporter lock held, and each player through the Doctor's screening (`ACCESS.md`). *Rescues only*: the first of those. *Closed*: nobody beams aboard but an admin; open her the night of your event. |
| `AdirondackRescues` *Rescues before the Adirondack* | 1 one, 2 two, 3 three, 4 five | 3 | How many of her crew the players must bring home first. |
| `AdirondackUsers` *Adirondack: who may board* | names | empty | Empty: everybody who meets `AdirondackAccess`. Otherwise only these players, and they still have to meet it. Admins are never refused. |
| `AdirondackName` *Name of the ship in orbit* | text | Adirondack | What she is called. See *What things are called* below for what it reaches. |
| `CaptainTruth` *Captain tells the truth* | 1 Only once Shepard has, 2 When it is earned, 3 From the first conversation | 2 | When Captain Titus will say what really happened (`CAPTAIN.md`). |
| `HydroponicsWater` *Hydroponics tend themselves* | 1 Yes, 2 No | 1 | Whether her trays water and weed themselves. |

A world that was visiting her before clearance existed stays open
(`ACCESS.md` 4), except that *Closed* and a boarding list are yours and are
asked first.

### What the ship may do

| Setting | Values | Default | What it does |
|---|---|---|---|
| `BeamUp` *Beaming up from the ground* | true, false | true | Off: nobody beams up from the ground. They call a shuttle down and walk aboard. **Beaming down is never refused**, so nobody is shut in a ship somebody else sent up. |
| `Flight` *Flight* | true, false | true | Off: no shuttle is taken up. They are still driven, called down and sent back up. |
| `ShipWeapons` *Ship's weapons* | 1 Torpedoes and phasers, 2 Phasers only, 3 None | 1 | What a shuttle's seats may fire. The tractor beam is not a weapon. Hand phasers follow your server's own PvP rules. |
| `TorpedoFire` *Photon torpedo fire* | 1 Full, 2 Blast only | 1 | *Blast only*: the explosion without the fire that burns buildings down. Your server's own `NoFire` and safehouses already stop the burning. |
| `Shields` *Shields* | true, false | true | Off: a landed shuttle has no shields, and the helm cannot raise them. |
| `FlightHeight` *Hover height* | 1 two storeys, 2 three, 3 four, 4 five, 5 six, 6 eight | 4 | How high a shuttle hovers. Anything taller is a wall she stops in front of. |
| `PhaserCutting` *Phaser cutting* | 1 Trees, doors and ground, 2 Trees and ground, 3 Off | 1 | What a hand phaser cuts. Somebody else's safehouse door is refused whatever this says. |
| `Replicator` *Replicator* | 1 Patterns and energy, 2 Unrestricted, 3 Off | 1 | *Unrestricted* makes anything, for nothing. *Off*: the machines are scenery and say so. |
| `EMH` *Emergency Medical Hologram* | 1 Full, 2 Off | 1 | The Doctor, and with him the only cure for a bite. There is no setting that keeps him and removes the cure. |
| `Installations` *Installing machines in the world* | true, false | true | Off: no warp core, replicator or EMH kit can be installed in a building. Machines already standing stay and work, and may always be packed up. |

### Balance

New in 1.22, and **not yet played**. The third page: how much dilithium
there is in the world, and what the ship charges for everything she does.
The defaults are the mod as its author plays it, which is hard: **a town
holds one to five crystals, and a crystal is about one outing with the
shuttle.** Every number below is yours to move. A percentage is of the mod's
own price: 100 is as designed, 50 half, 200 double, 0 free.

**How much dilithium there is.** A crystal is 5,000 units of power, and
nothing aboard makes one.

| Setting | Values | Default | What it does |
|---|---|---|---|
| `LootDilithiumMin` *Dilithium in a town's loot: fewest* | 0 to 50 | 1 | The county is counted in districts 1,500 squares across, about a town each (Muldraugh, Rosewood, Riverside and March Ridge are one apiece; Louisville is half a dozen). All the containers of one district, between them, give up a number of crystals between this and the most, drawn once for each district when the world is made. |
| `LootDilithiumMax` *Dilithium in a town's loot: most* | 0 to 50 | 5 | The most. Both at 0: no crystal is ever found in a container. Both the same: every district has exactly that many. |
| `WildDilithium` *Dilithium in the wild* | 1 Plentiful, 2 Scarce, 3 None, 4 Very rare | 4 | Crystals on natural ground, placed as players first load it. *Plentiful* is one to about 28 by 28 squares of field or wood, *Scarce* one to 55 by 55, *Very rare* one to 350 by 350. |
| `ProbeFind` *Probes that find dilithium* | 0 to 100 per cent | 30 | How many probes in a hundred come back with a dilithium fix. A save's first probe always finds something, and a long run of empty ones is followed by a find (six at 30, two at 90). At 0 only that first probe finds any. |
| `RaidCrystal` *Raid crates with a crystal* | 0 to 100 per cent | 10 | The chance a raid's outpost has a crystal in one of its crates. |
| `StartCrystals` *Spare crystals at a commissioned start* | 0 to 10 | 1 | The spares in the warp core of a shuttle that starts *Commissioned*, beside the one burning. A cold, marooned or personal shuttle has none. Read once, when her cabin is first built. |

What the loot settings really do, since they are the ones that matter most:

- **Where a crystal is found has not changed**: a jeweller's gem case, a pawn
  shop, an electronics store, a mechanic's shelves, a tool crate. The loot
  tables still roll them. The server counts each one as it is rolled and
  takes back any past the district's number before a player sees the
  container, so the part of a town the crew reach first is where its
  crystals are.
- **It is a ceiling the loot is expected to reach, not a promise.** A real
  town has hundreds of containers that can roll a crystal and will reach its
  number. A crossroads with one garage may never reach 1.
- **Loot respawn does not bring them back.** A district that has given up
  its number gives up no more, whatever is rolled there later.
- **A change is for what is still to be found.** Raise the most and
  districts already emptied have more to give; lower it and nothing already
  found is taken away. A world that had the mod before 1.22 keeps the
  crystals already lying in its containers.
- **The server's log counts them**: `[TREK] lode: a dilithium crystal is in a
  container at X,Y -- 2 of 4 for district 7,6`.

**What everything costs.** Each group is a percentage of the mod's own
prices, and the menus and panels show the price your setting gives.

| Setting | Default | What it scales, and the price at 100 |
|---|---|---|
| `CostReplicator` *Cost: replicator* | 100 | Every replication, by the item's weight: a bandage 25, a tin of beans 60, a hammer 120, a shotgun 220, nothing over 1,500. |
| `CostTransporter` *Cost: transporter* | 100 | A beam, each way, each person: 75. The hatch is always free. |
| `CostFlight` *Cost: flight and driving* | 100 | Calling her down 400, sending her up 150, starting her engine 50, taking off 300, a square driven 1.5, a square flown 4, a game minute in the air 3. |
| `CostShields` *Cost: shields* | 100 | A zombie pushed away 5, a point of crash damage mended 3. |
| `CostWeapons` *Cost: ship's weapons* | 100 | A photon torpedo 250, a bolt of her phasers 15, a second of the tractor beam 10. Hand phasers draw nothing from the ship. |
| `CostMedical` *Cost: the Doctor* | 100 | Projecting him 300, a treatment 100, a detox 400, the biofilter screening 150. |
| `CostSystems` *Cost: other systems* | 100 | Fabricating a probe 1,500, recharging a perimeter sentry 750, an android's charge, the galley's fridge and range. |
| `PowerUse` *Power use* | 1 Normal | 1 Normal, 2 Half, 3 A quarter, 4 None, 5 Double, 6 Four times: everything at once, on top of the groups above. *None*: a ship with power never runs down; a dark one still needs its first crystal. This one is applied as the charge is taken, so menus show the price before it and the note after a charge says what was really spent. |
| `CureCrystals` *Crystals a cure costs* | 1 | 0 to 5 spare crystals for the Doctor's cure for infection, spent when it starts. |
| `CureHours` *Hours a cure takes* | 12 | 1 to 168 game hours the patient stays aboard. |

Each takes effect at once, for the next charge. A price is never under 1
unless you made it 0. One you have raised past the 5,000 a crystal holds is
one no ship can pay, and is refused with its numbers.

**What the defaults add up to.** An outing (call her down, take off, fly 500
squares, hover an hour, fifty zombies off the shields, a scrape mended, four
beams, the Doctor and one treatment) is about 4,100 units of a crystal's
5,000. Before 1.22 it was 1,800, a replicated hammer was 24 and a torpedo
was free.

**The mod as it was before 1.22**, for a server that liked it:

```lua
LootDilithiumMin = 50, LootDilithiumMax = 50, WildDilithium = 2,
ProbeFind = 90, RaidCrystal = 25, StartCrystals = 3,
CostReplicator = 20, CostTransporter = 33, CostFlight = 40, CostShields = 40,
CostWeapons = 33, CostMedical = 30, CostSystems = 17,
```

(`CostWeapons` cannot make only the torpedo free again; 0 frees her phasers
and the tractor with it.)

**What the balance page does not reach**: how much one crystal holds, what a
hand phaser, a hypospray or a sentry can do, what a new cabin's armoury is
issued, and the Adirondack's own stores. See *What the mod does not do*.

### Content

New in 1.22, and **not yet played**. The fourth page: what of the mod is in
your world at all. Every switch is a tick box, on by default, and **a switch
you throw stops what is new and takes nothing away**: what a player already
holds, and a hull or a breaker box already standing, stay.

**The big four.**

| Setting | Off |
|---|---|
| `Shuttles` *Shuttles* | There is no shuttle on the server. None is set down (cold or marooned), none is issued to a player, nobody has the Shuttlecraft menu, and every command about one is refused: *There are no shuttles on this server.* Anybody aboard one when you throw it may still beam down or step out. A hull left on the ground stays as scenery. |
| `Adirondack` *The ship in orbit* | The U.S.S. Adirondack is not there: nobody boards her but an admin, she never calls a PADD, and there are no distress calls, rescues or raids. The same as `AdirondackAccess = 4`, `CommsFirstDay = 6`, `DistressCalls = false` and `Raids = 1` at once. |
| `FieldStation` *Field station* | No breaker box is hung in Muldraugh, and the station under it cannot be entered. |
| `Aliens` *Aliens* | No alien species for any character (as all ten species switched off: *Who your players may be*, below), and none of the dead are Borg. Humans are then allowed whatever `SpeciesHuman` says. |

They are separate on purpose. The shuttle's transporter is the way up to the
ship in orbit, so with `Shuttles` off she is out of reach whatever her own
switch says; the field station has its own way in and stays.

**Items.** Each weapon has a switch of its own, and everything else goes by
family.

| Setting | What it switches |
|---|---|
| `ItemBatleth`, `ItemMekleth`, `ItemLirpa`, `ItemUshaanTor` | The four blades, one each. |
| `ItemPhaser`, `ItemPhaserRifle` | The hand phaser, and the rifle. |
| `ItemKlingonDisruptor`, `ItemKlingonRifle`, `ItemRomulanDisruptor`, `ItemPolaronRifle`, `ItemCardassianPhaser` | The alien arms, one each. |
| `ItemSentry` | The perimeter phaser sentry. |
| `ItemsMedical` | The hypospray, the dermal regenerator, the medical tricorder. |
| `ItemsInstruments` | The tricorder, the PADD, the shoulder lamp. |
| `ItemsUniforms` | The six uniforms, the field pack, the holster. |
| `ItemsFieldKit` | The engineer's satchel, its five tools, the stem bolts. |
| `ItemsFood`, `ItemsDrinks` | The ration pack and the galley's dishes; its drinks. |
| `ItemsContraband` | Ketracel-white, felicium, Trellium-D, cordrazine, the Ktarian game, latinum, the three bottles. |
| `ItemsFarming` | The seeds of the seven hydroponics crops. |
| `ItemsKits` | The warp core, replicator and EMH station kits. |

What "off" means for an item:

- **A new cabin's lockers are not issued it**, nor the ship in orbit's
  stores, nor a raid's crates. A cabin already built keeps what it was
  stocked with: a cabin is stocked once.
- **No replicator makes it.** It leaves the catalogue at once, and comes
  back when the switch does.
- **It is not found in the world's loot** (next).
- **Nothing is taken from anybody.** A bat'leth in a player's hands is
  theirs.
- **Not reached**: what a profession starts a character with on the
  creation screen (a Starfleet officer's uniform), the phaser the ship's own
  guns are modelled on, and anything another mod hands out.

Dilithium, tapes, the PADD's story pieces, the pattern enhancers and the
installed machines themselves have no switch: they are the mod's workings,
not its equipment.

**Her things without her.**

| Setting | Values | Default | What it does |
|---|---|---|---|
| `ItemLoot` *Items in the world's loot* | 0 to 100 per cent | 3 | **Only with `Shuttles` off**, so that there is no ship to issue them. The chance that a container in a fitting kind of room holds one of the items you have left on. |

Where: weapons and the sentry in gun stores, police, army and security
stores and pawn shops; the medical set in pharmacies and hospitals; the
field kit, the instruments and the three installation kits in tool stores,
garages and mechanics'; uniforms in clothing stores and laundries; bottles
in bars and liquor stores; ration packs in groceries and restaurant
kitchens; seeds in garden and farm stores; contraband in motel rooms. One
item to a container at most, picked evenly from what is allowed there. With
a shuttle on the server none of this happens: her lockers are the source.

**Only the bat'leth**

```lua
Shuttles = false, Adirondack = false, FieldStation = false, Aliens = false,
ItemLoot = 5,
ItemMekleth = false, ItemLirpa = false, ItemUshaanTor = false,
ItemPhaser = false, ItemPhaserRifle = false, ItemKlingonDisruptor = false,
ItemKlingonRifle = false, ItemRomulanDisruptor = false, ItemPolaronRifle = false,
ItemCardassianPhaser = false, ItemSentry = false,
ItemsMedical = false, ItemsInstruments = false, ItemsUniforms = false,
ItemsFieldKit = false, ItemsFood = false, ItemsDrinks = false,
ItemsContraband = false, ItemsFarming = false, ItemsKits = false,
WildDilithium = 3, LootDilithiumMin = 0, LootDilithiumMax = 0,
```

One gun-store or police-locker container in twenty then holds a bat'leth,
and nothing else of the mod is in the world. (The last line takes the
crystals out too: with no ship and no kits there is nothing to burn them
in.)

**Ships, and no aliens**: `Aliens = false`, and the four alien-made blades
and the five alien arms off if you mean their things as well.

**The items and the species, and no ships**: `Shuttles = false,
Adirondack = false, FieldStation = false`. The installation kits turn up in
tool stores, so a crew can still build a replicator at home and feed it the
crystals they find.

### Cabins

New in 1.22, and **not yet played**. What the inside of a ship is. **Each of
these is read once, when a ship's cabin is first built, and that cabin is
hers for good**: changing one later changes only cabins nobody has stood in
yet. A cabin is lived in, and a setting must not move the locker somebody
filled.

| Setting | Values | Default | What it does |
|---|---|---|---|
| `CabinStyle` *Cabin style* | 1 Her hull's, 2 Any by chance, 3 Starfleet, 4 Klingon, 5 Vulcan | 1 | Whose hands built her bulkheads, her deck, her pad and every fitting. *Her hull's*: a Starfleet shuttle has a Starfleet cabin, a Klingon raider a Klingon one, a Vulcan ring ship a Vulcan one. |
| `CabinLayout` *Cabin layout* | 1 Shuffled, 2 Standard | 1 | *Shuffled*: the four fittings along her port bulkhead (stasis unit, range, sink, sick bay cabinet) stand in an order of her own, one of twenty-four. *Standard*: every cabin is the same one. |
| `CabinGalley` *Cabins have a galley* | on, off | on | The stasis unit, the range, and the ship's rations in the cupboard under the sink. Off: none of them. The replicator is `Replicator`'s to decide. |
| `CabinWater` *Cabins have running water* | on, off | on | The sink makes its own water. Off: it is a dry cupboard. |
| `CabinMedical` *Cabins have a sick bay* | on, off | on | The sick bay's cabinet with its Starfleet medical set, and the biobed. Off: neither. The Doctor is `EMH`'s to decide. |

A Klingon's and a Vulcan's cabin are furnished with that people's own
pieces: a forged-armour stasis unit, weapons rack, range, throne and
surgeon's slab on dark plate and an oxblood deck; or bronze and sandstone
cabinets, an arched bunk and a healer's bed on dark stone.

Whatever the style, a cabin has the same things in it and each works as it
does in Starfleet's: the armoury and its issue, the bunk, the tape rack and
the television, the transporter pad, the warp core, the replicator and the
Doctor's station. The three machines and the television are drawn as
Starfleet's in every cabin.

**What these do not do.** A cabin that was already standing when you
installed 1.22 is the standard Starfleet one and stays so. An admin who
refits a ship as another kind of hull (*Repainting a shuttle*, below) does
not change the cabin she already has. **An admin can rebuild any cabin as
any style, whenever they like**: *Rebuilding a cabin*, below.

### The campaign

| Setting | Values | Default | What it does |
|---|---|---|---|
| `StartState` *How the shuttle starts* | 1 Cold start, 2 Commissioned, 3 Marooned | 3 | The shared shuttle, in a **new** world only. *Cold*: landed near the first player, dark. *Commissioned*: overhead, powered, with the spares `StartCrystals` gives her (*Balance*). *Marooned*: dark, lost at one of six places, and nobody has a Shuttlecraft menu until they have walked aboard her (`MAROONED.md`). |
| `DistressCalls` *Distress calls* | true, false | true | Off: the ship hears none, so there is nobody to rescue. Rank and the default Adirondack clearance both come from rescues: with this off, set `AdirondackAccess` to 2 or 4. |
| `CommsFirstDay` *When the Adirondack first calls* | 1 Straight away, 2 a day, 3 three days, 4 a week, 5 two weeks, 6 Never | 4 | *Never*: Lt. Shepard does not call. A crew may still hail her, and the story is where it would have been. |
| `Raids` *Raids* | 1 Off, 2 Rare, 3 Normal, 4 Frequent | 3 | How often Captain Titus asks for help with the pattern buffer (`RAIDS.md`). |
| `RaidSize` *Raid size* | 1 Small, 2 Normal, 3 Large | 2 | How many of the dead a raid beams in. |
| `Borg` *Borg among the dead* | 1 As common as police, 2 Scarce, 3 Common, 4 None | 1 | How many of the world's zombies are Borg (`BORG.md`). With *None*, the Doctor's screening needs no sample. |

### The server itself

| Setting | Values | Default | What it does |
|---|---|---|---|
| `SpeedCheck` *Speed anti-cheat* | 1 Relax for the transporter, 2 Leave it as set | 1 | *Relax*: a server whose `AntiCheatSpeed` kicks or bans is set to log while it runs. *Leave it*: your own setting, and beams are rationed (next row). |
| `TransporterLimit` *Transporter charges* | 1 Match anti-cheat, 2 Always unlimited | 1 | When the check still kicks or bans, each player gets 3 beams with one back every 150 seconds, and a fourth is refused ("recharging") rather than the server kicking them. |

### Who your players may be

Each of these is on the *roleplay* page as a tick box, on by default.

| Setting | What it is |
|---|---|
| `SpeciesHuman` | A character with no species trait. **Off: aliens only.** |
| `SpeciesVulcan`, `SpeciesKlingon`, `SpeciesAndorian`, `SpeciesBetazoid`, `SpeciesTrill`, `SpeciesBajoran`, `SpeciesTalaxian`, `SpeciesOrion`, `SpeciesAndroid`, `SpeciesExBorg` | The ten species (`TRAITS.md` 4.2). |
| `TraitTransporterPhobia`, `TraitRealFoodOnly`, `TraitSpacesick`, `TraitStarfleetAcademy`, `TraitHoloHistorian`, `TraitTurboliftPhobia` | The six traits anybody may take (4.3). |
| `ProfessionCommand`, `ProfessionHelm`, `ProfessionEngineer`, `ProfessionSecurity`, `ProfessionMedical`, `ProfessionScience`, `ProfessionSurvey` | The seven Starfleet professions (4.4). |

**What switching one off does.**

- **The creation screen leaves it off its lists.** A player joining your
  server does not see a species, trait or profession you have switched off.
  A trait picked in a saved build comes off, and gives its points back.
- **The server takes it off a character who has it anyway**, within a game
  minute of seeing them, and tells them why. That is the rule; the screen is
  the courtesy. It also covers characters made before you changed the
  setting.
- **Humans off, and a character with no species** is given one of the
  species you allow, at random, and told which. If you switch off humans and
  every species, the rule cannot be met and humans are allowed.
- **A profession switched off** costs a character who has it the division's
  trait and the rank they started with. They keep their skills, their kit
  and any rank their rescues have earned.

What it cannot give back: the points a trait cost, and the skills and
vanilla traits a species brought (a Vulcan's strength), were spent on the
creation screen and are the game's own. A character given a species by the
server gets the look and everything the mod does for that species, and not
the creation screen's skill bonuses. Set your rules **before** players make
characters and none of this arises.

Vanilla's own traits and professions are not the mod's to switch.

### What a setting cannot do

- **Restock or rebuild.** A cabin, once built, is its crew's. No setting
  refills a locker or moves a fitting.
- **Change how a world began.** `StartState` is read once, when the world is
  new.
- **Take a personal shuttle's cabin away.** See below.

---

## A shuttle each

With `PersonalShuttles` set to 2 or 3, players the setting covers each get a
shuttle of their own. The shared shuttle stays, and `Access` still decides
who may use it; to have personal shuttles and no shared one, set
`Access = 3` and leave `AccessUsers` empty.

**What a player gets.** Within a game minute of the server first seeing
them, a note: *a shuttle has been assigned to you*. She is overhead,
commissioned, with one crystal's charge in her core, no spares and two
probes. They call her down or beam up as they would the shared one. Her
cabin is her own: its lockers and what is in them, her warp core and its
crystals, her replicator, her Doctor, her course and logged positions, her
shields, her flight.

**Whose she is.** Her owner's, and whoever they make crew
(*Shuttlecraft ▸ Crew*, aboard her). An admin may use any of them. Nobody
else: a stranger who asks her hatch to open is told they are not on her
crew.

**Which ship a menu means.** The one a player is standing or sitting in.
On the ground, the hull under the cursor, whoever's it is: walking up to a
shuttle and asking for its door is choosing it. Otherwise their own, and a
player who may use more than one has *Hail another shuttle* on the ground
menu, which also says in its title which ship it is speaking to.

**What every ship shares.** The story is the world's, not a ship's: the
distress calls and rescues, the channel to the ship in orbit, her clearance,
the probes' contacts on the map and the replicator's patterns are one of
each, whichever shuttle a player is aboard. One probe is away at a time,
whoever launched it.

**What does not change.**

- A shuttle is given **once, for the life of the save**. Her berth is where
  her cabin stands with everything her owner keeps in it, so it is never
  given to anybody else.
- **Taking a player off the list impounds her.** She and her cabin stay
  where they are, and neither her owner nor her crew may use her until the
  name is back on the list. Anybody aboard may always leave. An admin may
  still use her.
- There are **64 berths**. The sixty-fifth player is not given one, and the
  server's log says so.
- **Single player has one ship**, whatever this is set to.

**Telling them apart.** Every shuttle is one hull in one of eighteen
skins: six liveries (Fleet, Sciences, Operations, Medical, Tactical, Survey),
each kept, worn or derelict. Nobody has to choose: the shared shuttle wears
the fleet's and each personal shuttle the next livery round, so two on one
street are not the same ship twice; and a ship that began dark is worn, one
that was lost is a derelict until she is commissioned and worn after. See
*Repainting a shuttle* below to choose for them.

**Known limits, new in 1.21.0 and not yet played.**

- A shuttle flying is drawn at her height on the machines of the players
  dealing with her. To a player dealing with a different shuttle she is
  drawn on the ground beneath where she is. Her shadow and her position are
  right; her height is not.
- The first cabin a player enters after a server restart is built as they
  arrive, like the shared one. A cabin nobody has stood in does not exist
  yet, and costs nothing.

---

## Repainting a shuttle

New in 1.22, and **not yet played**. An admin has one more line on the
ground menu: right-click the ground, or a shuttle's hull, then
*Shuttlecraft ▸ Repaint her hull*, a livery, and a state. It is not a
sandbox setting, because it is about one ship and not the server.

- **What kind of ship.** The same menu's first level is the kind: a
  *Starfleet shuttle*, a *Klingon raider* (three liveries) or a *Vulcan ring
  ship* (three). A kind is a hull: whichever she is, she seats four, flies,
  lands on the same ground and has the same cabin, power and crew. Her kind
  is hers until an admin changes it.
- **Which ship.** The one the menu is speaking to: the hull under the
  cursor, or the admin's own (*A shuttle each*, above). On a hull it is that
  shuttle, whoever's she is.
- **When it shows.** A shuttle standing on the ground with nobody aboard is
  set down again where she stands, at once, facing north. One overhead, in
  the air, or with somebody in her wears it the next time she is set down;
  the admin is told which.
- **It is hers until it is given back.** *As she has earned it* at the top
  of that menu returns her to the skin the mod works out for her.
- **Only an admin** sees the line or is listened to. In single player it is
  the player's own world, and the line is always there.
- **A reward, a rank, a faction.** This is how to hand a player a ship that
  looks like something: give them a shuttle (`PersonalShuttleUsers`), then
  repaint her. There is no setting yet that does it by itself.

The server's log has a line for every repaint, and for every shuttle set
down: `skin N asked for, and the engine has her in skin M of 18`.

### Rebuilding a cabin

The same menu has *Rebuild her cabin*, aboard her or on the ground: a style
(*Starfleet*, *Klingon*, *Vulcan*), then *Standard layout* or *Shuffled
layout*. With the hull's line above it, an admin can put together any craft
the mod has: a Klingon raider with a Vulcan cabin, if that is the story.

- **Nothing a player owns is lost.** Before the old fittings come out,
  everything her lockers, stasis unit and cupboards held is put on her
  transporter pad, and a tape in her television with it. What somebody
  built aboard or dropped on her deck is not touched.
- **The new cabin is stocked as a new ship's is**: its armoury, its rations
  and its medical set are issued again. So a rebuild is also a second issue
  of the ship's gear, lying beside the first on the pad. It is an admin's
  tool; use it knowing that.
- **Its amenities are the server's settings today** (*Cabins*, above), not
  the ones the old cabin was built under.
- **Shuffled is rolled again every time**: ask twice and she may be laid out
  two ways.
- **When it happens.** At once if anybody is aboard her. With nobody aboard
  her cabin is not in the world to be rebuilt, so it waits, and is done the
  moment somebody next boards; the admin is told which.
- **Only an admin** sees the line or is listened to; in single player it is
  the player's own.

---

## What things are called

**The quick way: `AdirondackName`.** Set it and the ship in orbit has your
name everywhere the mod itself draws text: every menu and note, the
channel, the Captain, her crew's talk, the PADD (transcripts included), the
panels. Capitals follow: *ADIRONDACK* on a title card becomes your name in
capitals.

It does not reach the text the game draws without asking the mod: a tape's
subtitles **on the television** (ten lines name her), item tooltips (one),
a trait's description (one) and the sandbox page itself. Those need the
next section.

## Your own lore

Every word the mod shows is a translation key: the channel, the Captain,
9,000 lines of crew talk, every tape, every item's name. The game reads
every enabled mod's translation files in the order the mods are listed, and
a later mod's text **replaces** an earlier one's, key by key. So a small mod
of your own, listed after `TrekShuttle`, that carries the same keys with
your words in them, rewrites as much of the mod as you like, in any
language, and reaches everything including the television.

That mod is a **lore pack**, and the repository makes one for you
(`github.com/ElliotTheGreek`, `tools/make_lore_pack.py`; it needs Python and
nothing else):

```sh
# every line the mod has, in English, ready to edit
python tools/make_lore_pack.py out --id MyServerLore --name "My Server: Shuttlecraft lore"

# only the story: the channel, the Captain, the crew and the tapes
python tools/make_lore_pack.py out --id MyServerLore --what lore

# a rename, everywhere, and nothing else in the pack
python tools/make_lore_pack.py out --id Saratoga --rename "Adirondack=Saratoga" --rename "Titus=Okonkwo"

# in French, starting from the mod's own French where it has it
python tools/make_lore_pack.py out --id LoreFR --lang FR --what lore

# check it before you publish it
python tools/translations.py check-pack out
```

It writes a complete mod: `mod.info` (which requires `TrekShuttle`, and so
loads after it), the text as JSON under
`42/media/lua/shared/Translate/<LANGUAGE>/`, and a `README.txt` with these
steps. Then:

1. **Edit the text** on the right of each line. Never the key on the left.
   **Delete what you do not mean to change**: a key you leave out keeps the
   mod's own text, and a small pack survives the mod's updates.
2. **Keep in every line you edit**: `%1` and `%2` (the game fills them in),
   `{a}`, `{doc}` and the like (a crew member's name), no per-cent sign, one
   line. A key ending `_O1`, `_O2` is a button: sixty letters at most.
   `check-pack` refuses a line that breaks one of these and says which.
3. **Players see their own game language.** Write your words into every
   language folder your players use (`--lang ALL` writes them all), or a
   player in another language sees the mod's own text in theirs.
4. **Publish it** on the Workshop (unlisted is fine) and list it after the
   mod:

```ini
Mods=TrekShuttle;MyServerLore
WorkshopItems=3801178990;<your item's id>
```

**What is in the files.**

| File | Holds |
|---|---|
| `Print_Text.json` | The channel to the ship in orbit (`..._COMM_...`), Captain Titus (`..._CAPT_...`), and everything the crew say (`..._CREW_...`). |
| `Recorded_Media.json` | Every tape: its label, and each subtitle (`RM_TREK_...`). |
| `IG_UI.json` | Menus, notes and panels. |
| `ItemName.json`, `Tooltip.json`, `UI.json`, `Sandbox.json`, `Recipes.json`, `Fluids.json`, `Farming.json`, `ContextMenu.json` | As named. `UI.json` has the species, traits, professions and ranks. |

**What a lore pack cannot change** is what happens: which line follows
which, what an answer leads to, what a tape does to whoever watches it. That
is the mod's structure (`content/README.md`), and changing it is a fork.
You can make a line say anything; you cannot make the Captain keep a
different secret. The canon the story was written against is `LORE.md`.

---

## Recipes

**A roleplay server: Starfleet officers only, a shuttle for the captain,
the ship in orbit for events**

```lua
PersonalShuttles = 3, PersonalShuttleUsers = "captain_reyes",
Access = 3, AccessUsers = "captain_reyes;cmdr_oyelaran",
AdirondackAccess = 4,           -- closed until the night
DistressCalls = false, CommsFirstDay = 6, Raids = 1,   -- your story, not the mod's
StartState = 2,
```

On the night, set `AdirondackAccess = 2` from the admin panel, and
`AdirondackUsers` to whoever is invited.

**Aliens only, and only some of them**

```lua
SpeciesHuman = false,
SpeciesAndroid = false, SpeciesExBorg = false, SpeciesOrion = false,
```

**No aliens at all**

```lua
SpeciesVulcan = false, SpeciesKlingon = false, SpeciesAndorian = false,
SpeciesBetazoid = false, SpeciesTrill = false, SpeciesBajoran = false,
SpeciesTalaxian = false, SpeciesOrion = false, SpeciesAndroid = false,
SpeciesExBorg = false,
```

**A shuttle for everybody, and no flying over the safehouses**

```lua
PersonalShuttles = 2, Flight = false, ShipWeapons = 3, BeamUp = true,
```

**A PvP server that wants the shuttle and none of its guns**

```lua
ShipWeapons = 3, TorpedoFire = 2, PhaserCutting = 3, Shields = false,
```

**A hard server**: the defaults are one already. Harder still:

```lua
StartState = 3, Replicator = 1,
LootDilithiumMin = 0, LootDilithiumMax = 2, WildDilithium = 3, ProbeFind = 15,
CostReplicator = 200, PowerUse = 5,
BeamUp = false,                 -- find her, walk to her, call her down
AdirondackAccess = 1, AdirondackRescues = 4, Borg = 3, RaidSize = 3,
```

**A relaxed server**: the ship as a convenience, not a budget.

```lua
StartState = 2, StartCrystals = 3, WildDilithium = 2,
LootDilithiumMin = 5, LootDilithiumMax = 12, ProbeFind = 75,
PowerUse = 3,                   -- a quarter of every price
```

**A building server**

```lua
StartState = 2, PowerUse = 4, Replicator = 2, Borg = 4, Raids = 1,
AdirondackAccess = 2, DistressCalls = false,
```

**Your own ship, your own story**

Set `AdirondackName`, and ship a lore pack made with
`--rename "Adirondack=Saratoga" --rename "Titus=..." --rename "Shepard=..."`,
then rewrite the tapes and the channel in it to taste.

---

## Languages

Each player sees their own game language, for everything the mod shows.
Nothing needs setting on the server. The game falls back to English key by
key, so a line a language does not have yet is in English, never missing.

**The mod carries all 27 of the game's languages**, machine-translated
(2026-10-12) and not yet read by a speaker of each: see the last paragraph
of this section if a line is wrong in yours.
`python tools/translations.py status` says how much of each the mod carries,
and `python tests/test_translations.py` holds every one against the
English: every key there, the same
placeholders, every button short enough to be a button.

**What the server writes is put into words by the player's machine.** A
note the server sends carries a key, not a sentence, so a French player on
a German server reads French. The panels wrap languages written without
spaces (Chinese, Japanese, Thai) between characters.

**What stays English, and why:**

- **Proper names**: the ship, her people, Starfleet, Kentucky.
- **A crew member's or an ensign's own name**, which the server draws from
  one list.
- **What is painted on the mod's own pictures**: LCARS labels drawn into a
  texture, the registry on the hull.
- **The development build's own menu**, which only the author sees.

**If a line is wrong in your language**, the texts are plain JSON, one
folder a language, under `42/media/lua/shared/Translate/<LANG>/`.
Corrections are welcome on the Workshop page or on GitHub. Or put it right
for your own server today with a lore pack.

---

## When something goes wrong

The mod's lines in `server-console.txt` and a client's `console.txt` start
`[TREK]`. A broken invariant is `[TREK] WARN`.

| Line | Means |
|---|---|
| `[TREK] ship authority ready (server, v1.21.0, build 36) ...` | It loaded. No such line: the mod is not on the server. |
| `[TREK] void map 'TrekShuttle' is loaded` | The map is in `Map=`. `NOTICE: the 'TrekShuttle' map is not loaded` means it is not. |
| `[TREK] speed anti-cheat set from kick (2) to log (3) ...` | `SpeedCheck = 1` at work. |
| `[TREK] fleet: <name> has a shuttle of their own, ship N, overhead` | A personal shuttle issued. |
| `[TREK] ship N (<name>'s) ready: ...` | At a start: a personal shuttle's record woken. |
| `[TREK] WARN ... every one of the 64 shuttle berths is taken` | The sixty-fifth player. |
| `[TREK] rules: <name> is no longer vulcan -- not a species on this server` | A rule took a species, a trait or a posting off a character. |
| `[TREK] rules: <name> had no species and humans are not allowed; they are <species> now` | A species given. |
| `[TREK] creation: the server's rules applied ...` (client) | The creation screen left your switched-off choices off its lists. |
| `[TREK] <name> now owns the shuttle` | The shared shuttle's first user, under `Access = 2`. |
| `[TREK] power: <what> refused -- N needed, M left` | A ship could not pay for something. N is the price your balance page gives; `PowerUse` scales what it takes. |
| `[TREK] lode: a dilithium crystal is in a container at X,Y -- 2 of 4 for district 7,6` | A crystal rolled into loot and kept: the second of the four that district will ever give up. |
| `[TREK] core: the ship is issued N spare crystal(s)` | `StartCrystals`, read as a commissioned shuttle's cabin was first built. |
| `[TREK] salvage: TrekShuttle.TrekBatleth is in a container in a gunstore` | `Shuttles` is off and `ItemLoot` put one of the mod's things into rolled loot. |

A player told *There are no shuttles on this server* met `Shuttles = false`.
A player told *You are not on this shuttle's crew* is on the wrong side of
`Access`, or asked a personal shuttle that is not theirs. One told *the
Adirondack is taking nobody aboard* met `AdirondackAccess = 4`; *not on her
boarding list* met `AdirondackUsers`.

Reports with those lines are what gets things fixed: the Workshop page's
comments, or GitHub.

---

## What the mod does not do

- **Balance past the balance page.** How much a crystal holds (5,000), a
  hand phaser that never runs out, a hypospray that refills itself, a
  sentry's twenty-five shots, what the armoury of a new cabin is issued, and
  the fifty crystals the ship in orbit starts with are the mod's own and
  have no setting yet.
- **Take back what a switch stops.** Switching an item, the shuttle or the
  field station off stops new ones; it removes nothing already in the
  world or in a player's hands.
- **Per-player rules.** A species is allowed for everybody or nobody; there
  is no "only this player may be a Klingon". The lists are for who has a
  shuttle and who may board, not for who may be what.
- **An admin's menu in the game**, but for one line: *Repaint her hull*,
  above. Every rule is a sandbox setting, changed from the game's own admin
  panel. There is no in-game tool for giving one player a rank, a species or
  a second shuttle.
- **Change a cabin that has been built, by a setting**: its style, its
  layout and its amenities are settled the first time somebody boards her.
  An admin's *Rebuild her cabin* is the way.
- **A cabin of a different size or plan** for a kind of ship, or a piece one
  people has and another has not.
- **A shuttle that wears as she is flown**, a livery a player picks for
  themselves, or one a setting hands out.
- **More than one shared shuttle**, or a personal shuttle with a different
  cabin from the rest.
- **Change the story's structure from a setting.** Words, yes (a lore
  pack). Which call follows which, no.
