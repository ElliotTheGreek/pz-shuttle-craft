# Traits — species, divisions and rank

Researched, designed and **built** on 2026-09-24. Section 2 is what the
engine does, checked against the 42.20 jar and vanilla's own scripts and Lua.
Section 3 was the menu of ideas; **section 4 is what was actually built**, with
the numbers, the files and what is still to see in game. Where section 3 and
section 4 disagree, section 4 is right.

The rules in `DEV_GUIDE.md` and `MULTIPLAYER.md` bind as always. The one that
decides the most below is the first: **the server owns the change, a client
asks.** A trait is character state and an appearance is world-visible state,
and both have vanilla sync paths that run from the server.

---

## 1. The canon constraint

`COMMS.md` 6.1 says first contact is "where the player decides who they are" --
a native of this county, a Starfleet officer, or nobody's business -- and that
**the mod never adjudicates it**. Traits are the one feature that could break
that, because a trait is an answer written into the save.

So, settled by this document's own reading of that line:

- **A species or Starfleet trait is the player's claim, made at character
  creation, and it is theirs to make.** It is the same decision 6.1 offers,
  taken earlier. The mod may *read* it; it must never contradict it, and it
  must never demand one.
- **A native with no Trek trait at all is a first-class character.** Nothing
  in the ship may require a species, a division or a rank. Vanilla's
  professions stay in the list, and the Kentucky mechanic is as welcome aboard
  as the Vulcan.
- **The mod explains no species.** How a Vulcan came to be standing in
  Muldraugh, and who they are to anyone in the lore, is for the player to
  imagine. No tape, line or item ties a species to a character in the story,
  and no species is written as kin to anyone. The mod doesn't need the answer,
  and supplying one would be adjudicating 6.1 by the back door.
- **Nothing here touches a bite.** The EMH is the only cure (`EMH.md`), and
  that is what the whole of `LORE.md` is built on: the horde is Borg
  nanoprobes and a morphogenic virus grafted together. No species gets an
  immunity, however canon-plausible. The same goes for anything that looks
  like one from outside: resistance, slower conversion, a better survival
  roll.

---

## 2. What the engine does

### 2.1 Traits are a registry plus a script block

Before 42.13, traits were made in Lua with `TraitFactory.addTrait` and checked
with `HasTrait("Name")`. **That API is gone.** Since 42.13 a trait is a
namespaced id in a registry, defined by a script block.

**The registry file.** `ModRegistries.init()` walks every enabled mod and runs
`<versionDir>/media/registries.lua`, falling back to the `common` folder
(bytecode, and the literal `"/media/registries.lua"` in the class). It runs
before scripts load, and a script naming an unregistered trait fails with a
null `characterTraitType`. `RegistryReset.createLocation` refuses the `base`
namespace: *"Default namespace '%s' is not allowed!"*.

```lua
-- TrekShuttle/42/media/registries.lua
TREK_Registries = TREK_Registries or {}
TREK_Registries.Traits = {
    VULCAN = CharacterTrait.register("trek:vulcan"),
}
```

`CharacterTrait.register(String)` is `register(false, id)`: a static that
builds a `CharacterTrait` and puts it in `Registries.CHARACTER_TRAIT`. The same
file can register `CharacterProfession`, `ItemBodyLocation`, `MoodleType` and
`ItemTag` ids.

**The script block** has the same shape as vanilla's
`media/scripts/generated/characters/character_traits.txt`:

```
module TrekShuttle
{
    character_trait_definition trek:vulcan
    {
        IsProfessionTrait = false,
        DisabledInMultiplayer = false,
        CharacterTrait = trek:vulcan,
        Cost = 4,
        UIName = UI_trait_trek_vulcan,
        UIDescription = UI_trait_trek_vulcanDesc,
        XPBoosts = Strength=1,
        MutuallyExclusiveTraits = trek:klingon;trek:andorian,
        GrantedRecipes = ...,
        GrantedTraits = base:...,
    }
}
```

- **`Cost`**: a negative cost gives points back, which is what makes a trait a
  bad trait.
- **`GrantedTraits` works on a trait, not only on a profession.** Vanilla uses
  it twice: `obese` grants `overweight`, `veryunderweight` grants
  `underweight`. So a species can be a bundle of vanilla traits, and every one
  of them already works, is already balanced and already syncs. **This is the
  cheapest way to give a species an effect.** One thing to confirm in game:
  that character creation applies the grant for a trait the player picked, as
  it does for those two.
- **`IsProfessionTrait = true`**: the trait comes only with a profession and
  never appears in the list.

**The text** goes in `media/lua/shared/Translate/EN/UI.json`. It has been JSON
only since 42.15, and the mod's translations are already there.

**The icon** is `media/ui/Traits/trait_<name>.png`, 18x18. Vanilla's are in
that folder.

**Working example on this machine.** Bandits Week One (Workshop 3403180543,
the `42.20` folder) ships three custom traits the whole way through:

- `media/registries.lua`: `CharacterTrait.register("BWO:charming")`
- `media/scripts/bwo_traits.txt`: the definition block
- `media/lua/shared/Translate/EN/UI.json`: the name and description
- the trait checked with `character:hasTrait(BWORegistries.CharacterTraits.CHARMING)`

Read that before building. It is the whole feature in four files.

### 2.2 Using a trait at runtime

- **To check one:** `character:hasTrait(TREK_Registries.Traits.VULCAN)`. It
  takes the object, not a string. `TREK_Padd.lua` already checks
  `CharacterTrait.FAST_READER` the same way.
- **The trait set:** `IsoGameCharacter.getCharacterTraits()` returns a
  `CharacterTraits` with `add`, `remove`, `get` and `set`. It has
  `save`/`load` and `write`/`read`, so it is saved with the character and goes
  over the wire with it.
- **Adding a trait after creation** does not apply its XP boosts by itself.
  Vanilla's admin stats panel does `add`, then
  `modifyTraitXPBoost(trait, false)`, then `SyncXp(char)`. That call site is
  in an admin panel, so per *The jar is not the API* it proves reachability
  and nothing else. Disassemble `modifyTraitXPBoost` before relying on it.
- **Effects are ours to write.** There are no trait hooks. A trait "does"
  something because code asks `hasTrait` in the right place: an event,
  a timed action, a mod function. That is the design constraint on section 3,
  and the reason the good ideas there hang off systems the ship already has.

**Multiplayer:** a trait added at runtime is added on the server. A
promotion (3.3) is a server handler that validates the request and changes the
trait set. Whether the change reaches the owning client at once or on the next
player sync is **not yet measured**. Community code (BodyCountRewards) logs
that "the engine may not have synced yet". Test it on the local dedicated
server before anything reads a trait the same tick it was added.

### 2.3 Professions

`character_profession_definition` in vanilla's
`media/scripts/generated/characters/character_professions.txt`, registered with
`CharacterProfession.register("trek:...")`:

```
character_profession_definition trek:engineer
{
    CharacterProfession = trek:engineer,
    Cost = -4,
    UIName = UI_prof_trek_engineer,
    IconPathName = profession_trek_engineer,
    GrantedTraits = trek:starfleet;trek:engineering,
    XPBoosts = Electricity=3;Mechanics=2;MetalWelding=1,
    GrantedRecipes = ...,
}
```

**Starting clothes.**
`media/lua/shared/Definitions/TraitClothingSelectionDefinitions.lua` maps a
trait to clothing offered at character creation, per sex and per body
location, with a chance. The uniforms (`UNIFORMS.md`) already exist in three
division colours, so a division trait can offer its own duty uniform on the
creation screen. That is one table entry per division.

### 2.4 Appearance: do not replace the head

The human is one skinned mesh (`Skinned/MaleBody`, `Skinned/FemaleBody`), and
there is no head slot. Body-replacement mods on the Workshop are client-side
only: every player enables them before joining, and running them on a server
does nothing. That cannot give one player ridges and another antennae on the
same server. **Rule it out.**

**Body visuals are the route.** They are how vanilla draws stubble:

```
item M_Beard_Stubble
{
    DisplayCategory = MaleBody,
    ItemType = base:clothing,
    BodyLocation = base:zeddmg,
    ClothingItem = M_Beard_Stubble,
    WorldRender = false,
    hidden = true,
}
```

- **Attaching one:** character creation calls
  `desc:getHumanVisual():addBodyVisualFromItemType("Base.M_Beard_Stubble")`
  (`CharacterCreationMain.lua:1973`).
- **What a body visual is:** an `ItemVisual` in `HumanVisual.bodyVisuals`, and
  `HumanVisual.save` writes that list. It is not in the inventory, so it
  cannot be taken off, dropped, stolen or burned, and it persists.
- **A texture-only one:** stubble's clothing XML has no model at all, only
  `<m_BaseTextures>body\stubble\m_beard_stubble</m_BaseTextures>`, a texture
  painted over the skin. That is exactly the right shape for Trill spots, a
  Bajoran nose ridge painted on, or Betazoid eyes (if the eyes are on the body
  texture; unchecked).
- **A mesh one** needs a model:
  `<m_MaleModel>media\models_X\Skinned\Clothes\...</m_MaleModel>`, like
  vanilla's `Hat_BunnyEarsBlack.xml` with `<m_AttachBone>Bip01_Head</m_AttachBone>`.
  Vulcan ears, Klingon ridges and Andorian antennae are all this.

The Workshop has already done this: Fantasy Bodyparts (3589269108) does elf
ears, horns and a skin tint, Draenei Parts (3647846467) does blue skin and
pointed ears, and Elf Ear (3426237563) is marked multiplayer. They use
clothing items in custom body locations. Body visuals are this document's
preference because nothing can take them off. **Which one works under a hat
is the first thing to test** (`m_HatCategory` and the masks folder decide
it).

**Blue skin has two routes, and the second is new:**

1. **An overlay texture** in `m_BaseTextures`, tinting whatever of vanilla's
   five tones is under it. Draenei Parts does this.
2. **`HumanVisual.setSkinTextureName(String)`.** `getSkinTexture()` opens with
   `if (skinTextureName != null) return skinTextureName` (bci 0-11), **before**
   it looks up the five-tone list in `PopTemplateManager.maleSkins`. So a named
   texture replaces the skin outright. That means a whole blue
   `AndorianMaleBody.png`, painted from `MaleBody01.png`, rather than a tint.
   `HumanVisual.save` writes the field, so it persists. Vanilla calls it only
   on an animal corpse (`ButcheringUtil.lua:581`), so for a player, whether
   the network visual carries it is **unmeasured**.

**Models** go through the same pipeline as the phaser (`tools/bake_phaser.py`),
with one difference: they are *skinned*, not static. They need:

- the `Bip01` armature, weighted to `Bip01_Head`;
- a single material, which is all the engine supports;
- export as `.X` or `.fbx`;
- an entry in `media/fileGuidTable.xml` whose GUID matches the XML's `m_GUID`.

### 2.5 Appearance in multiplayer

Vanilla's own non-admin actions show the pattern. `ISCutHair`, `ISDyeHair`,
`ISTrimBeard` and `ISWashYourself` all change the visual inside a timed action
and then call `sendHumanVisual(self.character)`. `ISCutHair` and `ISDyeHair`
are things every player does, which is the call site this project's rules
require (not the admin health cheat in `ClientCommands.lua`, which also calls
it). So:

1. A species trait is read on the **server**, in `OnCreatePlayer` or the
   first player update after it.
2. The server adds the body visual (or sets the skin name) if it is not
   already there. The check makes it idempotent, and that doubles as the
   repair pass for an existing save.
3. `sendHumanVisual(player)`, then `resetModelNextFrame()`.

Every client needs the mod's assets, and a Workshop subscription provides
them.

**Unmeasured, and to test on the local dedicated server before any modelling:**

- whether a new character's visual is complete by the time `OnCreatePlayer`
  runs there;
- whether a custom `ItemBodyLocation.register("trek:ears")` or vanilla's
  `base:zeddmg` is the right slot for a permanent feature;
- how a mesh body visual draws under a hat and a hood.

---

## 3. Speculation

Ideas only. Every effect is written against something the engine or the ship
already has, because an effect that needs a new system is a new system, not a
trait. Costs are guesses on vanilla's scale.

### 3.1 Species

A species is a trait. A player with none is human, and that costs nothing.

| Species | Look | Effect ideas | Why it fits here |
|---|---|---|---|
| **Vulcan** | pointed ears (mesh) | grants `strong` or `stout`, and `brave`; `fastreader`; **feels the cold** (a Kentucky winter against a desert world). Negative: will not eat meat without an unhappiness hit | the PADD and the tape shelf reward a reader |
| **Klingon** | forehead ridges (mesh) | `strong`, `thickskinned`, `fasthealer` (redundant organs), `heartyappetite`, a blade XP boost. Negative: **replicated food is an insult**, an unhappiness hit on anything from the replicator | gives the replicator a rival; the ship's blades are already in its patterns |
| **Andorian** | antennae (mesh) + blue skin (2.4) | `keenhearing` (the antennae), **shrugs off cold, suffers heat**, aggressive melee boost | the showpiece: the only one that needs both halves of the appearance work |
| **Betazoid** | black irises (texture, if the eyes are on the body texture) | **empath:** the living ensign's position without the tricorder at short range; stress near a panicking crewmate | read-only effects on systems that already exist (`ENSIGN.md`) |
| **Trill (joined)** | spots down the temples and neck (**texture only**) | **past hosts:** three random +1 XP boosts, rolled once at creation. A different Trill every time | the cheapest species to build: no mesh at all |
| **Bajoran** | nose ridges (texture, maybe a small mesh) + an earring as a real starting item | a lower boredom/stress floor (faith), `outdoorsman` (a resistance fighter's childhood) | the earring is a plain vanilla-style item; no body location puzzle |
| **Talaxian** | mottled spots (texture) + whiskers as a **custom beard style** (`beardStyles.xml`, no body location needed) | **the galley's best friend:** Cooking +3 and the cook-trait recipes; a forager and a haggler's eye (Foraging +1). **Morale officer:** crewmates within a few tiles lose boredom and unhappiness a little faster. Negative: `weak` (a small people), or a hearty appetite | the galley is real now (`ENERGY.md` phase 8); the morale aura is the one multiplayer-shaped trait in the list |
| **Orion** | green skin (the Andorian's skin route, 2.4) | **smuggler:** Nimble, Sneak and Lockpicking boosts, and vanilla burglar's hot-wiring (the ship's tricorder already opens electronic locks, so this is the manual version); males can take `strong`. Negative: **pheromones.** They work on anything that breathes, and the dead follow the scent. A faint, periodic attraction around the player: zombies drift toward an Orion the way they drift toward a noise | the negative is the fun part: a stealth species with a scent to manage. The attraction is the one effect here that needs real engine work: a small world sound from the server, measured |
| **Android** | pale gold skin and yellow eyes (**texture only**, the skin route) | see **3.1a**: too strong as a bundle, so it has to cost something the others don't | the best-loved and the hardest to balance |
| **Liberated Borg** | ocular implant (mesh) | `nightvision`. **Hears the horde:** a low hum near large groups | **Careful:** this must never touch bites (section 1), however plausible an immunity sounds |

**Recommended first species: Trill**, because it proves the whole path with no
model. After that, Vulcan, because one head-weighted mesh proves the rest. The
Andorian is last: the blue skin question (2.4) has to be answered before it is
worth modelling. The Orion and the android use the same skin route, and wait
on the same answer.

### 3.1a The android

As a bundle of vanilla traits, a Soong-type android is simply better at
everything: `strong`, `fastlearner`, `brave`, `nightvision`, never panics,
never bored. No point cost pays for that, because Project Zomboid's costs are
balanced against survival and an android barely has to survive. The answer is
not to shave the positives until it is a strong human. **Give it a weakness
that no other character has, and make that weakness the ship.**

**It runs on the ship's power, not on food.**

- **Hunger and thirst are replaced by charge.** An android never eats or drinks;
  it runs down instead, a little faster than a human gets hungry. The mod
  holds hunger and thirst at zero and keeps a charge value of its own.
- **Charge comes only from the ship.** Aboard, it recharges in place of sleep:
  lying on the biobed, or at a charging alcove, it draws from the same power
  bus as the galley and the replicator (`ENERGY.md`). **So an android spends
  the ship's dilithium**, and a crew with one aboard burns crystals faster.
  That is the real cost: every point of an android's strength is paid for in
  the one thing the replicator can't make.
- **Running down is a slope, not a cliff.** Low charge slows it (the endurance
  and speed penalties of tiredness), and flat is unconsciousness, like
  sleep. An android that walks too far from the shuttle has to be carried
  home, or the ship called down beside it.
- **It does not heal by itself.** Wounds stay open until someone repairs
  them: the Doctor, an engineer at the workbench, or a regenerator in a
  crewmate's hands. **A bandage does nothing**, because there is nothing under
  it to knit. Rest aboard repairs slowly.
- **It is heavy and loud.** It moves with vanilla's `clumsy`, and doesn't
  sneak well.
- **It still turns.** Section 1 holds. A bite is a bite, and the Doctor is
  still the only cure. That makes the only thing it cannot survive the same
  thing that kills everyone.

What it is good at, once all that is paid for: `strong`, `fastlearner`,
`nightvision`, never panics, never bored or unhappy, reads at twice the speed.
**Cost: high, perhaps +10.** It's still a deal only for a crew who keep a
supply of dilithium.

**What the engine has to do**, and why this is a system rather than a trait:

- Holding hunger and thirst at zero means writing a player's stats every
  minute (`getStats():set(CharacterStat.HUNGER, 0)`). Which process owns a
  player's stats in 42.20 is **not yet measured**. If it is the owning client,
  this is client code about its own character, which the rules allow
  (`DEV_GUIDE.md`: a client moves only its own character). Measure it before
  writing it.
- Charge is one number per player. It belongs in player mod data, written on
  the server (see *Player mod data a client writes is not the server's*), and
  shown in a small moodle.
- "Does not heal by itself" means undoing the engine's healing each tick on
  every body part, which is the heaviest piece here. **A lighter version:**
  keep vanilla healing, and make only bandages and first aid useless.
- **An android lite, if the full version is too much:** keep food and sleep
  (Data did eat, from a nutrient suspension, and could sleep), and bundle
  `strong`, `fastlearner`, `brave` and `nightvision` against `clumsy`, "bandages
  do nothing", and a hefty cost. It is less interesting, but it is a weekend
  rather than a project.

**Recommendation:** the full version. It is the only species whose cost
changes how a crew plays the ship, and that's what a species trait in this
mod should do.

### 3.1b A taste of home

**Built on 2026-09-24: the food, and then the preferences (4.2).** The galley
now carries a dish for every species above, each one canon from on screen
(Memory Alpha, with the episode in the item's comment in `trekshuttle.txt`).
Until the traits exist, every character eats them at the numbers in the
script. This section is how a species would change that.

| Species | Its food in the galley | Canon |
|---|---|---|
| Vulcan | plomeek soup | ENT, and everywhere |
| Klingon | gagh, rokeg blood pie; bloodwine, raktajino | TNG "A Matter of Honor" |
| Andorian | Andorian tuber root; Andorian ale | DS9 "Second Sight"; ENT "Cease Fire" |
| Betazoid | oskoid | TNG "Menage a Troi" |
| Trill | balso tonic (canon has no Trill dish) | TNG "The Host" |
| Bajoran | jumja stick, hasperat | DS9; TNG "Preemptive Strike" |
| Talaxian | steamed chadre'kab, leola root stew | VOY "The Raven"; "State of Flux" |
| Orion | wing-slug roll (canon's only Orion food) | LD "Shades of Green" |
| Android | nutrient suspension | TNG "Deja Q" |
| Human | ration pack, Earl Grey | - |

**The rule:** a species that eats its own food
is buffed, and one that eats *another* species' food is unhappy about it.

- **Its own food:** a further `UnhappyChange` of -15 and `StressChange` of
  -10 on top of the item's numbers. This is comfort food, a long way from
  home.
- **Another species' food:** +10 unhappiness. The gagh's tooltip ("You are not
  a Klingon") becomes true for everyone except a Klingon, and the same goes
  for every alien dish.
- **Kentucky's food is neutral** for everybody. Nobody starves into misery
  because the Muldraugh supermarket doesn't stock plomeek. The preferences
  touch only the galley.
- **A human has no preferences** at all: the base numbers, both ways. It's
  the default character, and the one with the widest palate.
- **Exceptions that are the fun:**
  - **Klingon:** replicated food of any kind is an insult (3.1). That
    includes their own dishes out of the replicator, and not the ones found
    in the rations locker.
  - **Vulcan:** meat is the penalty, rokeg pie most of all.
  - **Trill:** never takes the foreign-food penalty. Several lifetimes of
    other people's cooking, and Jadzia loved Klingon food.
  - **Android:** no sense of taste, so neither the buff nor the penalty. In
    the full version (3.1a) it doesn't eat at all, and the nutrient
    suspension becomes its fuel.

**The mechanism is one engine hook, and it runs where the rules want it.** An
item script line `OnEat = <global Lua function>` is resolved by name when the
food is eaten. `IsoGameCharacter.Eat` (bci 764-800) reads
`Food.getOnEat()`, looks it up with `LuaManager.getFunctionObject`, and
`pcall`s it with the food, the character and the fraction eaten. `Eat` runs
where the eating action completes, which in build 42 is the server
(*A timed action is rebuilt on the server*). So one shared function reads the
eater's species trait, looks the item up in a table of whose food it is, and
applies the adjustment, scaled by the fraction eaten. The one galley
table replaces a line in every item.

**To check before building:**

- Vanilla's own `OnEat` values are Java (`RecipeCodeOnEat.consumeNicotine`).
  Whether `getFunctionObject` resolves a mod's *Lua* global, and a dotted one
  like `TREK_Food.onEat`, needs a test. A plain global name is the safe
  choice.
- Mood writes on the server have to reach the client: the same
  `sendSyncPlayerFields` question 2.2 raises, and `Eat` itself calls it at
  bci 729. That's a hint the path exists.
- A replicated dish has to be told apart from a looted one, for the Klingon.
  Whether the replicator marks what it makes is unchecked. If it doesn't, one
  line of item mod data at replication does the job.

### 3.2 Divisions: Starfleet professions

The uniforms already set the three divisions and their colours: command red,
operations gold, sciences teal. A profession per role inside each, each
granting a hidden `trek:starfleet` trait and a division trait, and each
offering its duty uniform at creation (2.3).

| Profession | Division | Skills | Ship hook |
|---|---|---|---|
| **Flight controller** | command | Driving, Aiming | a faster top speed at the helm, or a better speed band (`PILOTING.md`) |
| **Command officer** | command | a little of everything | a server-side say in who is crew (the owner-and-crew setting already exists) |
| **Engineer** | operations | Electricity, Mechanics, Metalworking | load and pull crystals faster; a small cut on replicator cost (`ENERGY.md`) |
| **Security officer** | operations | Aiming, Short Blade, Fitness | phaser training: the phaser's handling or its sound radius (`PHASERS.md`) |
| **Medical officer** | sciences | First Aid 4 | the hypospray and regenerator work faster in their hands; the medical tricorder reads more (`MEDICAL_SET.md`) |
| **Science officer** | sciences | a reading and a foraging boost | tricorder range, and probe odds (`PROBES.md`) |
| **Cultural survey specialist** | sciences | reading, trapping or foraging | **Shepard's own job.** Knows the 1990s: faster tape transcription, and a line in the channel that recognises a colleague |

And the one that answers 6.1 the other way: **no profession at all.** A
Kentucky nurse is still a nurse.

### 3.3 Rank

**Not picked at creation.** A rank you choose on a menu is a costume, and
`UNIFORMS.md` already parks rank insignia as "cosmetic until a crew-role
system gives it a purpose". This is that purpose.

**Field commissions.** Voyager is the precedent: a stranded ship gave the
Maquis Starfleet ranks because it needed a crew. The *Adirondack* is stranded,
has eleven crew on the ground, and has a stranger aboard her shuttle. So:

- **Everyone starts unranked**, native and officer alike. The field commission
  is issued by Shepard over the channel after the first rescue, and it works
  the same whatever the player told her in 6.1. It does not adjudicate: *"I
  don't care what you were. You're an ensign now."*
- **Rank is a hidden trait, added and removed at runtime by the server** (2.2):
  `trek:ensign`, `trek:ltjg`, `trek:lt`, `trek:ltcmdr`, and perhaps
  `trek:commander` at the top. A promotion swaps one for the next. It shows in
  the character's info panel for free.
- **Earned from what the ship already counts:** rescues (`THANKS`), the six
  fragments (`CONVERT`), days survived with the ship. No new counters.
- **The pips are a small mesh on the uniform collar.** That might be a body
  visual that only draws with the uniform, or a variant texture on each
  uniform. Both need 2.4's test first.
- **Rank's effects stay social, or small.** Shepard's lines address the rank;
  in multiplayer the most senior aboard gets the first seat on the helm chart.
  **No rank gates anything a crewmate needs**: in co-op, locking the replicator
  behind a pip is punishing your friends.

### 3.4 Trek traits anyone can take

Human or not, Starfleet or not. These are the cheapest and probably the most
fun, because each is a single `hasTrait` in code that already exists.

| Trait | Cost | Effect | Hook |
|---|---|---|---|
| **Transporter phobia** | -2 | beaming costs stress and a moment's panic (Barclay, TNG "Realm of Fear") | the transporter's one code path |
| **Real food only** | -1 | replicated food leaves you unhappy (Sisko's father's restaurant) | the replicator's output |
| **Spacesick** | -2 | nausea in the air: the shuttle in flight, not on the ground | the hover state (`PILOTING.md`) |
| **Starfleet Academy** | +2 | knows the ship: the replicator's catalogue opens on its known patterns, the helm needs no tutorial | a UI default, nothing more |
| **Holo-historian** | +1 | tapes on the shelf give more of their effect, once | the tape reading (`LORE.md`, `PADD.md`) |
| **Tribble magnet** | -1 | ... | no. |

---

## 4. What was built

Three commits: the galley's third course (`8f0be89`), the traits (`14f68b5`)
and the looks (`cb16748`). Every number below lives in `TREK_Config.lua`
under *Traits*.

### 4.1 Where it lives

| File | Job |
|---|---|
| `media/registries.lua` | every id: 27 traits, 7 professions. Runs before anything else |
| `media/scripts/trek_traits.txt` | the definitions: cost, XP boosts, granted vanilla traits, exclusions |
| `shared/TREK/TREK_Traits.lua` | asking (`has`, `species`, `rank`), the mirrored stat change, the table, the small factors, two-way exclusions at boot |
| `server/TREK/TREK_TraitsServer.lua` | first sight, the timers, the android, rank, the transporter hook |
| `server/TREK/TREK_Appearance.lua` | the look: skin, overlays, meshes |
| `client/TREK/TREK_TraitsUI.lua` | applies the server's mirrored change and shows the notes |
| `shared/Definitions/TREK_ProfessionClothing.lua` | the uniforms on the creation screen |
| `tools/gen_trait_icons.py` | trait and profession icons |
| `tools/gen_species.py`, `tools/preview_species.py` | the looks, and a sheet of every species to judge them by (`design/art/species/`) |

**The one rule every effect follows:** the server decides, applies it, and
sends the owning client the same change for its own copy of the character
(`T.adjust`). Single player applies it once. The tests delete each half in
turn and fail.

**Every path is unique, not only the namespace.** The engine drops the
namespace in two places: a trait's icon is `trait_<path>.png`, and a
profession's creation clothing is `ClothingSelectionDefinitions[<path>]`.
`test_assets.py` fails if any path matches a vanilla trait or profession.

### 4.2 Species

| Species | Cost | The engine's part | The mod's part | Look |
|---|---|---|---|---|
| Vulcan | 8 | Strength +2; Brave, Fast Reader | meat of any kind is unhappy | ears |
| Klingon | 7 | Strength +1, Long Blade +1; Thick Skinned, Hearty Appetite | replicated food is an insult | brow ridges |
| Andorian | 6 | Short Blade +1; Keen Hearing, Outdoorsman | - | blue skin, antennae |
| Betazoid | 3 | First Aid +1 | senses the live rescue, direction only, every half hour within 120 tiles | dark eyes |
| Trill | 5 | - | three random skills +1 level, once; never minds foreign food | spots |
| Bajoran | 4 | Sneak +1, Aiming +1; Outdoorsman | stress and unhappiness ease every ten minutes | nose ridges |
| Talaxian | 2 | Cooking +2, Foraging +1; the cook's recipes; Hearty Appetite | crewmates within six tiles shed boredom and unhappiness | mottled scalp |
| Orion | 3 | Nimble, Sneak, Lightfoot +1; Burglar (hot-wiring) | a small world sound every ten minutes, off the ship | green skin |
| Android | 12 | Strength +2; Fast Learner, Brave, Night Vision, Fast Reader, Clumsy | no hunger or thirst; a charge (below) | pale gold skin |
| Liberated Borg | 3 | Night Vision | the hum near fifteen or more of the dead, at most hourly | ocular implant |

**The android** runs down from full in a day and a half. Asleep aboard, it
charges ten points an hour at two units of the ship's reserve a point. Below
25 it is held tired, and at nothing exhausted. It is told at 50, 25, 10 and 0.
It still turns if bitten.

**The table** (3.1b) is built as designed, and it reaches every food:
vanilla's `ISEatFoodAction:complete()` is wrapped, so a Vulcan's tin of Spam
counts as much as their rokeg pie. The replicator stamps
`TREKReplicated` on what it makes, which is how a Klingon and Real Food Only
can tell.

### 4.3 Anyone can take

| Trait | Cost | What it does |
|---|---|---|
| Transporter Phobia | -2 | each beam up, down or descent: stress +0.25, panic +40 |
| Real Food Only | -1 | replicated food: unhappiness +15 |
| Spacesick | -2 | aboard in flight: stress and unhappiness every ten minutes |
| Starfleet Academy | 3 | Electrical +1, Aiming +1 |
| Holo-historian | 2 | PADD reading and transcription a quarter faster |
| Turbolift Phobia | -2 | each turbolift ride: stress +0.35, panic +60, unhappiness +10, and a warning in the lift's menu. The Jefferies tubes cost nothing (`JEFFERIES.md` 6) |

### 4.4 Divisions

| Profession | Cost | Skills | Division trait |
|---|---|---|---|
| Starfleet Command Officer | -4 | Aiming 2, Fitness, Nimble, First Aid | reports as a lieutenant (j.g.) |
| Starfleet Flight Controller | -2 | Aiming, Nimble 2, Mechanics 2 | the shuttle flies 20% faster with them at the helm |
| Starfleet Engineer | -6 | Electrical 4, Mechanics 2, Metalworking | every charge 10% cheaper while aboard (`P.pay`) |
| Starfleet Security Officer | -6 | Aiming 3, Reloading, Short Blade, Fitness | reports with a phaser |
| Starfleet Medical Officer | -4 | First Aid 5, Short Blade | reports with a hypospray |
| Starfleet Science Officer | -2 | Electrical, Foraging 2, First Aid, Trapping | reports with a tricorder that sweeps half again as far |
| Cultural Survey Specialist | 0 | Foraging, Trapping, Cooking, Tailoring | reports with a PADD; Holo-historian |

Each offers its division's duty uniform, and the dress uniform, on the
creation screen. Every Starfleet profession reports as an ensign.

### 4.5 Rank

Ensign, lieutenant (j.g.), lieutenant, lieutenant commander, commander, at
1, 3, 5, 8 and 11 rescues credited to the rescuer. A character's rank is
whichever is higher: where they started, or what their rescues are worth. It
is added and removed on the server, sent with `sendSyncPlayerFields(0x07)`,
and announced to that player alone. A native is unranked until their first
rescue, and then holds a field commission whatever they told Shepard.

### 4.6 The looks

The engine's three mechanisms, as 2.4 found them, all saved with the
character:

- **A recoloured skin**: 30 textures, 3 species x 2 sexes x 5 tones.
- **An overlay**: 12 hidden body-visual items, 6 kinds x 2 sexes.
- **A head mesh**: 2 items, each carrying both sexes' models, with 5 texture
  choices following the skin tone.

`gen_species.py` places everything by anatomy measured in the body meshes,
never by eye, because the two sexes' atlases are packed differently.
`TREK_Appearance.apply` is a check rather than a one-shot. It runs on first
sight and every ten minutes, changes only what is wrong, and leaves another
mod's skin alone.

### 4.7 Not built, on purpose or for now

- **Temperature.** The Vulcan feeling the cold and the Andorian suffering the
  heat. The Andorian has Outdoorsman instead; body temperature is a system of
  its own.
- **The android's bandage rule.** "It does not heal by itself" (3.1a). Its
  charge is built; undoing the engine's healing per body part is not.
- **Rank pips on the collar.** The rank shows in the character's traits, with
  pips for icons, not on the uniform.
- **Shepard addressing a rank.** Her lines are the channel's
  (`COMMS.md`); a rank is there to read when a thread wants it.
- **Talaxian whiskers.** The mottling is there. A beard style can be trimmed
  off (5), so the whiskers are not.
- **Drinks** have no preferences: a fluid is drunk, not eaten, and never
  reaches `ISEatFoodAction`.
- **The creation-screen avatar** shows no look. It is applied once the
  character is in the world, within a minute.

## 5. To see in game

The simulation holds the mod's side of all of it (the `traits`,
`traits_multiplayer` and `species_look` sections). What only the game can
show:

1. **The creation screen.** The species and traits are listed with their
   icons and costs; picking Vulcan greys out Weak, and Weak greys out
   Vulcan; the seven professions show their icons; a Starfleet profession
   offers its uniform under *Coveralls*.
2. **A Trill's first minute.** Three past hosts named in a halo note, and
   three skills a level higher on the skills panel. This is the one use of
   `addXpNoMultiplier`, and `getXpN` is assumed to be the next level's cost.
3. **The looks, in the world.** Every species, from the front and the side.
   The Vulcan ears and Andorian antennae sit on the head with no hat, and
   under a hat; a mesh body visual under a hat has not been seen. On a
   server, the other player sees them too (`sendHumanVisual`).
4. **Eating.** A Vulcan eating plomeek soup and then a steak; a Klingon
   eating replicated gagh. The halo note and the unhappiness moodle move on
   the eater's screen: the mirror at work.
5. **The android over a day.** No hunger, the charge notes, sleeping aboard
   filling it and the reserve going down.
6. **A rescue** promoting its rescuer, with the rank in their traits.
7. **The Orion's scent** does not bring more than a drift. The radius is 12
   (`C.OrionScentRadius`).

**Route in game, without a console:** a new character in a world with the
mod on picks a species on the traits page and a Starfleet profession on the
first page. Everything else follows once they are in the world. A character
from before the mod can't have traits added except by an admin, and their
look follows within ten minutes if one is.


---

## Sources

- **Engine:** `projectzomboid.jar` 42.20 via `tools/pzapi.py`,
  `tools/javarefs.py` and `tools/javadis.py`:
  - `ModRegistries.init`
  - `CharacterTrait.register`
  - `RegistryReset`
  - `CharacterTraits`
  - `HumanVisual.getSkinTexture`, `save` and `setSkinTextureName`
- **Vanilla:**
  - `scripts/generated/characters/character_traits.txt` and `character_professions.txt`
  - `scripts/generated/items/clothing.txt`
  - `clothing/clothingItems/M_Beard_Stubble.xml` and `Hat_BunnyEarsBlack.xml`
  - `lua/client/OptionScreens/CharacterCreationMain.lua`
  - `lua/shared/Definitions/TraitClothingSelectionDefinitions.lua`
  - `lua/shared/TimedActions/ISCutHair.lua` and `ISDyeHair.lua`
- **Workshop, installed:**
  - Bandits Week One (3403180543): a working 42.20 custom trait
  - HorseMod (3661336777): `registries.lua`
- **Web:**
  - [pzwiki: Creating a trait mod](https://pzwiki.net/wiki/Creating_a_trait_mod), [Registries](https://pzwiki.net/wiki/Registries), [Build 42.13.0](https://pzwiki.net/wiki/Build_42.13.0), [Creating a hair mod](https://pzwiki.net/wiki/Creating_a_hair_mod)
  - [TIS example registries.lua](https://github.com/pz-wiki-modding/Archive.Project-Zomboid-Modding/blob/main/TIS%20guides/B42%20unstable%20MP/testmod_registries/42/media/registries.lua)
  - [character_trait_definition](https://pz-wiki-modding.github.io/PZ-API-Docs/scripts/character_trait_definition.html)
  - [ADHD trait mod](https://github.com/JoshuaSHenderson/ProjectZomboid-ADHD-Trait), [BodyCountRewards](https://github.com/Lenniitsch/PZ-BodyCountRewards)
  - Workshop: [Fantasy Bodyparts](https://steamcommunity.com/sharedfiles/filedetails/?id=3589269108), [Draenei Parts](https://steamcommunity.com/sharedfiles/filedetails/?id=3647846467), [Elf Ear](https://steamcommunity.com/sharedfiles/filedetails/?id=3426237563), [Player Body Overhaul](https://steamcommunity.com/sharedfiles/filedetails/?id=3429790870)
  - [TIS forum: Blender to Zomboid](https://theindiestone.com/forums/topic/37647-the-one-stop-shop-for-3d-modeling-from-blender-to-zomboid/)
