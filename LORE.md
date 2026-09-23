# Lore — the tape shelf

The plan for telling stories aboard this ship, and the engine research it rests
on.

`ROADMAP.md` and `ROADMAP2.md` say what the ship *does*. This file says what it
**remembers**. Everything here is delivered through one fitting — a small shelf
beside the television in the bow — and a set of VHS tapes on it, each of which
is a piece of somebody's testimony.

The rules in `DEV_GUIDE.md` and `MULTIPLAYER.md` are binding as always: the
server owns the shelf, its contents and anything that appears in it later; a
client asks and displays. Read *Rules that exist because they were broken*
before starting anything below — three of them apply directly, and they are
named where they do.

---

## 1. Why tapes, and why this is cheap

Build 42 already has the whole feature. It has a recorded-media system with
per-line text, per-line colour, per-line effects on the player, per-player
"I have already heard this" memory, and **engine-side synchronisation of the
currently-playing line to every client in the room**. It is what the vanilla
VHS tapes and CDs run on, and the mod's television is already a real
`IsoTelevision` carrying `Base.TvWideScreen`'s device data, which declares
`AcceptMediaType = 1` — the tape type.

So the mod does not have to build a media player, a subtitle renderer, a
"watching" timed action, a progress store or a multiplayer path for any of it.
It has to write **text** and register it. That is the whole of the
implementation, plus one shelf and one item.

This is the cheapest large feature left in the project by a wide margin, and it
is the only one that adds nothing the player has to learn: they already know
what a television and a videotape are.

---

## 1a. The canon

Settled 2026-09-23 and binding on everything below. Four facts, and each one
pays for something the mod could not previously explain.

**The era is two generations on.** The mod is set roughly **forty to sixty
years after** TNG, Deep Space Nine and Voyager. Every Starfleet tape in the
shelf is therefore a fifty-odd-year-old recording of people who are history to
the pilot who collected them, and nobody aboard is contemporary with anybody on
the tapes. This is what makes the shelf an *archive* rather than a diary, and
it is why a talent night from stardate 44390.7 is a fifty-eight-year-old
curiosity rather than last month's party.

**The pilot is a historian by temperament.** She is a Starfleet officer on an
observation posting, and privately a buff — Starfleet history, and family
histories above all. That is the entire reason the shelf exists: the tapes are
*her collection*, not the ship's library, and it is why the bow of a shuttle
has a row of somebody's favourite recordings in it.

**The television is an anthropological artifact, and that is why it is aboard.**
This is the piece the mod has never accounted for: a Starfleet shuttle does not
ship with a 1993 television. She acquired the set and its tape deck *as
specimens* — the world she was sent to observe is so implausibly close to
Earth's own 1990s that the hardware is itself the finding — logged them as
surface artifacts, and then worked out what else the machine would play. The
collection followed the machine. So the tapes are genuine period cassettes with
her handwriting on them, which is also why the item borrows vanilla's cassette
icon and VHS box model rather than having art of its own.

**Tuvix has descendants, and one of them knew the pilot.** The line is on the
Voyager side: a lower-decks Betazoid crewman and Tuvix, in the eighteen days he
existed; their daughter, three ways split between Talaxian, Vulcan and Betazoid,
who was never in Starfleet; and *her* child, who was — and who was a friend of
the pilot's. That friendship is why a family-history assignment made by somebody
else's grandchild is sitting on this shuttle's shelf at all, and it is the hook
that ties the first tape to the last one.

### What the framing buys

It explains the medium, it explains why the tapes are *in the room* rather than
in a menu, it lets the shelf hold genuine 1993 Earth tapes alongside Starfleet
ones without a seam — and it gives the collection an owner, which is the thing
that turns a list of stories into somebody's shelf.

---

## 2. What was verified, and where

All of this is from the installed 42.20.4 — the bytecode, vanilla's own Lua and
the tile catalogue — not from a wiki. Each claim names what settled it.

### A mod registers media through a Lua event, not a file

`RecordedMedia.init()` (bytecode) does two things in order: `load()` the save's
own state, then

```
18  ldc  "OnInitRecordedMedia"
20  aload_0
21  invokestatic  LuaEventManager.triggerEvent(String, Object)
```

— it hands the `RecordedMedia` instance to Lua. Vanilla's own registration is
then ordinary shared Lua, in `media/lua/shared/RecordedMedia/`:

- `recorded_media.lua` fills a global table `RecMedia` — 760 KB of it, one
  entry per tape and CD;
- `ISRecordedMedia.lua` is thirty lines: on `OnInitRecordedMedia` it walks
  `RecMedia`, calls
  `_rc:register(category, id, itemDisplayName, spawning)`, sets
  `title`/`subtitle`/`author`/`extra`, and calls
  `data:addLine(text, r, g, b, codes)` for each line.

**So a mod adds keys to `RecMedia` from its own `shared/` Lua and vanilla
registers them for it.** No XML, no file format, no engine call of our own. We
should still add our own `OnInitRecordedMedia` handler as the belt to that
brace — see *the load-order question* in section 9.

### Any category that is not "cds" is the television type

This is the load-bearing fact, and it is four instructions long:

```
RecordedMedia.getMediaTypeForCategory(String)
  0  aload_0      ifnonnull -> 6
  4  iconst_m1    ireturn          ; null -> -1
  6  ldc "cds"    equalsIgnoreCase
 12  ifeq -> 19
 15  iconst_0     goto -> 20       ; "cds" -> 0
 19  iconst_1                      ; everything else -> 1
 20  ireturn
```

Media type 1 is the tape type. `ISDeviceMediaAction:isValid()` inserts a tape
only when `deviceData:getMediaType() == item:getMediaType()`, and the
television's device data comes from `Base.TvWideScreen`, which declares
`AcceptMediaType = 1`.

**Therefore the mod can invent its own category — `Trek-VHS` — and the cabin's
television will accept it, with no change to vanilla's own VHS pools.** A
custom category was the one thing that could have sunk this design, and the
engine simply does not check the name.

This is also the reverse of the shape `DEV_GUIDE.md` keeps warning about: the
method's *name* suggests a lookup table of known categories and its body is a
single string comparison. Read the bytecode, as ever.

### Line pacing is derived from the text's length

`DeviceData.updateMediaPlaying`:

```
172  String.length()  i2f
176  ldc 10.0   fdiv
180  ldc 60.0   fmul
184  putfield  DeviceData.lineCounter
     ... then clamped to [60 * minmod, 60 * maxmod]
```

and the counter is decremented by `1.25 * GameTime.getMultiplier()` per update.
So **a line's time on screen is proportional to its character count**, clamped
at both ends. Write lines, not paragraphs: a paragraph is one subtitle that
sits there for a very long time, and the clamp means a two-word line is not as
short as it looks either. The exact seconds are a stopwatch job in game and are
deliberately not asserted here.

### Playback is synchronised by the engine

The same method writes `currentMediaLine` and `currentMediaColor` and then
calls `transmitDeviceDataStateServer(...)`. **The crew watching a tape together
is the engine's problem, not ours** — which makes this the first feature in the
mod with a multiplayer story that needs no code at all. That is exactly the
kind of claim `ROADMAP.md` says wants checking with two machines, and it is on
the list in section 8.

### Effects are Lua, and the vocabulary is readable

`shared/RadioCom/ISRadioInteractions.lua` is the interpreter. A line's `codes`
is a comma-separated list; each token is three letters, an operator
(`+` `-` `=`), and an amount, and is **only parsed when the token is longer
than four characters** (so `BOR-1` works and `BOR-1` is the shortest legal
form). `=` sets the value instead of changing it.

| | |
|---|---|
| Stats | `ANG` `BOR` `END` `FAT` `FIT` `HUN` `MOR` `STS` `PAN` `SAN` `SIC` `PAI` `DRU` `THI` `UHP` |
| Skills | `SPR` `LFT` `NIM` `SNE` `BAA` `BUA` `CRP` `COO` `FRM` `DOC` `ELC` `MTL` `FKN` `CRV` `AIM` `REL` `FIS` `TRA` `FOR` `TAI` `MEC` `CMB` `SPE` `SBU` `LBA` `SBA` `MAS` `POT` `BLA` `GLA` `HUS` `BUT` `TRK` |
| Recipes | `RCP=<recipe name>` — `player:learnRecipe`, with a halo |

Four numbers that decide how a tape is written:

- **A skill code of `+1` is 50 XP** (`doSkill`: `amount = 50 * _amount`). One
  coded line is nothing; a training tape is thirty of them.
- **Skill XP stops at `SandboxVars.LevelForMediaXPCutoff`, which is 3 in every
  vanilla preset.** Training tapes are an early-game item by the engine's own
  design, and no tape can carry anybody to a high skill. That is a feature and
  the tape list leans on it.
- **A stat code's step is small**: `_amount * 0.05` for a 0-1 stat,
  `_amount * 5` for panic, `_amount * 5` for boredom and unhappiness.
- **The per-code cooldown is ~30 frames**, set to 30 on firing and decremented
  `1 * multiplier` per `OnTick`. It is a debounce, not a rationing system, so a
  code on every line does fire on every line.

### A line is learned once per character, for ever, and its identity is its translation key

`checkPlayer` opens with

```lua
if player:isKnownMediaLine(_guid) then return end
player:addKnownMediaLine(_guid)
```

where `_guid` is `MediaLineData.getTextGuid()` — **the line's translation key**.
Three consequences, and the second one is a trap:

1. **A tape's effects are a one-shot per character.** XP from tapes cannot be
   farmed by rewatching, and a player who has seen a tape gets nothing from it
   again. The writing therefore has to be worth watching once, not repeatedly.
2. **Two lines that share a translation key share their learning.** Vanilla
   does this deliberately — a CD's chorus is the same key every time it comes
   round, and only the first pass pays. So a refrain in one of our tapes is
   free to repeat, and **a key copy-pasted between two tapes silently makes the
   second tape's line inert**. Every key in this mod is prefixed and unique per
   line; `tests/test_assets.py` should fail a duplicate (section 7).
3. The known-line set is per-character and lives in the save, so it survives
   reconnects and is not ours to manage.

### The listener has to be near it, and "outside" has to agree

`OnDeviceText` walks the players and `playerInRange` requires the same `floor(z)`
and ±5 tiles in x and y. `checkPlayer` then returns early if
`source:isOutside() ~= plrsquare:isOutside()`.

The cabin **is not a building** (`DEV_GUIDE.md`: *A wall keeps a player in only
where the engine thinks there is a building*), so every square aboard should
answer the same way as every other and the check should pass trivially. That is
reasoning, not evidence, and it is the cheapest thing on the in-game list: if
tapes play with no halos and no XP anywhere aboard, this check is the first
suspect.

### Strings are translation keys, in their own category file

Every field vanilla passes to `register` and `addLine` is a key —
`RM_<guid>` — resolved out of
`media/lua/shared/Translate/EN/Recorded_Media.json`. Ours go in
`TrekShuttle/42/media/lua/shared/Translate/EN/Recorded_Media.json`, per
`DEV_GUIDE.md`, *Translations are one JSON file per category*.

The good news about this one: a missing key shows **the key itself** on screen.
Unlike the uniform GUID table, this failure is loud.

---

## 3. Where the tapes live

### The shelf

The bow row is `y = 0`. The deck plan today:

```
    0123
  0 TVTA        0,0 monitor wall   1,0 television on a low table
  1 F*.p        2,0 monitor wall   3,0 armoury
  2 oh.M
  3 wD.H
  4 m*.B
  5 R.@B
```

**The rack goes at 2,0: `location_shop_generic_01_1`, a video-shop display.**
Chosen for the silhouette — the brief was that it should look like the thing a
rental shop keeps tapes in — and out of `tools/_catalog/tiles.json`:

```
ContainerCapacity 20    container shelves    CustomName Shelves
GroupName "Comics Shop"    Facing S    solidtrans
```

Rows of things stood face-out, and `Facing S` is the way the bow bulkhead's
monitor banks and the television already face, so it sits against the forward
wall rather than at an angle to it.

**It is the only sprite in the game that reads as a media rack in one square.**
Everything else is two tiles: both Rental groups
(`location_entertainment_theatre_01_120..135`, the actual video-store racks) and
both magazine shelves carry `SpriteGridPos` pairs, and the bow row has no two
adjacent free squares — 1,0 is the television and 3,0 is the armoury. The
Fossoil magazine shelf is the near miss and is worth remembering: two tiles, but
**non-blocking**, and from the same tileset as the cabin's own walls.

**It blocks its square, and that costs one thing.** 2,0 was the only square a
player could stand on to open the **armoury** at 3,0, because 3,1 and 3,2 are
the other two lockers. The armoury is now reached **diagonally from 2,1**.
Vanilla kitchens are full of corner cabinets opened exactly that way, so this is
expected to be fine — but the engine's reach rule is not in Lua and has not been
read, so it is an **in-game check and not a proven fact**. The rack itself is
reached straight on from 2,1, which is the access that matters most, and the
swap back to a wall shelf is one sprite name if the armoury turns out awkward.

The monitor bank at 2,0 came back with the rack: it takes the floor, so there is
no longer a free deck square there to hang screens over.

One thing this deliberately avoided: **the television's own table.**
`furniture_tables_low_01_3` is `solidtrans` and carries **no** `container`
property, so the obvious "shelf under the telly" is not a container at all. That
is *A comment is not a container: check what the sprite actually is*, avoided by
looking it up first.

**Decided and built: the monitor bank at 2,0 came out.** Two wall-mounted
objects on one edge of one square is the kind of thing that looks like a bug
even when it is not, and three screens still read as a bulkhead of screens. The
bow row is now `T V L A` — monitor wall, television, tape shelf, armoury.

**The `.tbx` was edited by script, not in BuildingEd**, and that is a deviation
from *The interior is authored in BuildingEd, not in the code* worth recording
honestly. It is plain XML: a `<furniture>` block holding the rack's two
facings (appended, so its document index is 33, which is what
`<object FurnitureTiles="33">` means — `tools/import_tbx_layout.py` builds its
table from `root.findall("furniture")` in document order), `33` added to
`<used_furniture>` to keep that list a permutation of the block indices, and the
object at 2,0 repointed from block 1 to block 33. `orient` names the wall the
object stands against, so the set's two facings map to `N` (`_001`, facing south
off a north wall) and `W` (`_000`, facing east off a west wall) — the same
convention the bow's monitor banks already use.

`tools/import_tbx_layout.py` reads it back as `2,0 location_shop_generic_01_1
container=shelves` and `tests/test_layout.py`'s drift check passes both
ways, which is the evidence the edit was well formed. The old file is kept at
`TrekShuttle_Interior.tbx.pre-tapeshelf.bak`.

**One thing to do that a script cannot:** open the `.tbx` in BuildingEd once and
confirm it still loads and draws. Nothing here proves the editor is as tolerant
of a hand-written furniture block as the importer is.

### It reaches existing saves, unlike every other locker

`DEV_GUIDE.md`, *Never restock an existing container*: a container is stocked
when it is **created**. The shelf at 2,0 does not exist in any save today, so
`place()` returns `created = true` the first time the build pass runs after the
`C.BuildRev` bump, and it is stocked then — in an old save as much as a new
one. The tape shelf is therefore the **second** system in this mod to reach an
existing world, after the EMH, and for the same reason.

### The tape item

One new item, `TrekShuttle.TrekTape`, in `media/scripts/trekshuttle.txt`:

```
MediaCategory = Trek-VHS,
```

plus a 64×64 icon (`tools/gen_tape.py`, generated and keyed like everything
else — and vetted at 32px against the rest of the set, because that is where
`ROADMAP.md`'s own rule has caught three icons already).

A tape's **name in the inventory comes from its MediaData**, not from the item
script — `MediaData.getTranslatedItemDisplayName()` — so one item type is
enough for every tape in the shelf, and the shelf reads as a row of labelled
tapes rather than seventeen item scripts.

Stocking is a `special` rule in `TREK_Build.lua` (`SPECIALS.tapes`) rather than
a `C.Loot` list, because a fill that happens to miss a tape looks exactly like
one that did not — the argument that already makes the uniforms and the medkit
guarantees. **And the stock pass has to do one thing more than `U.stockEach`
does**: after creating each tape it must call

```lua
item:setRecordedMediaData(RecordedMedia:getMediaData(id))
```

and then **read it back and log the title it came out with**, in the
`B.stockReport()` tradition. A tape with no media data is a blank tape: it
sits in the shelf, it goes in the television, and nothing happens, with nothing
in the log. That is the seventh face of *present, drawn and inert* and it is
entirely predictable, so it gets the line that proves it worked.

Note on reachability: `setRecordedMediaData` has a vanilla Lua call site in
`client/Context/Inventory/InvContextMedia.lua`, but the branch around it is
gated on `getCore():getDebug() or isAdmin()`, which is the `getAllItems()`
shape (*A vanilla call site proves reachability, never correctness*). It is
reachable — the gate is on offering the menu, not on the method — and vanilla
also routes a client's version of it through a real
`sendClientCommand(player, "item", "changeRecording", ...)` server handler.
We call it on the authority, where the item is made, and we log the result. If
it ever answers nil, the fallback is `setRecordedMediaIndexInteger(index)` off
`getIndexForMediaData`.

---

## 4. What a tape has to be, to be worth writing

The standard, before any of the stories below get written:

- **A line is a shot, not a paragraph.** It is on screen for a time
  proportional to its length and then it is gone. Thirty to seventy characters.
- **Twenty to forty lines is a tape.** Long enough to be a sitting, short
  enough to finish. The one deliberate exception is in the list and the joke is
  that it cannot be finished.
- **Colour is the speaker.** `addLine` takes r, g, b per line and vanilla uses
  it for exactly this — a second voice, a caption, a title card. Two speakers
  and a caption colour is plenty; four is soup.
- **It is testimony, not narration.** Every tape is somebody talking, or
  somebody's camera left running. Nothing in the shelf is a lore dump written
  by the mod; it is all a person, on a bad day, mid-sentence.
- **It is original writing.** Not transcribed episode dialogue — which is both
  the legal answer and the better one, because a transcript is somebody else's
  scene with the life taken out of it. These are the gaps between episodes:
  the cousin, the training film, the memorial, the tape nobody meant to keep.
- **The effects are the last thing decided, not the first.** Write the tape,
  then ask what watching it does to a person, then pick the codes. A tape
  designed around `MEC+1` is a spreadsheet with a voice.

And one rule that is specific to this mod: **a tape may cost the player
something.** `UHP+1` is a legal code. The whole reason to put a shelf of
personal recordings on a ship in a world where everyone is dead is that some of
them should hurt to watch, and the game has a number for that.

---

## 5. The library

Seventeen tapes in three tiers. Ids are readable rather than GUIDs (vanilla's
keys are GUIDs, so there is no collision risk) and every one is prefixed
`TREK_`, because `FileGuidTable.mergeFrom` taught this project what an
un-namespaced id costs.

### Tier 1 — the ship's issue, on the shelf from the first arrival

**1. `TREK_Tuvix` — *Dear Grandpa Tuvix***

**A school assignment, and cheerful the whole way through.** This is the tape
the shelf is named for and the tone is the opposite of what the subject
invites: there is no anger in it, no grief, and nothing rehearsed. It is a
bright, slightly over-prepared kid delivering a genealogy project they got
genuinely interested in.

The shape, in their own order:

1. It is an assignment. They say so in the first ten seconds, the way you do.
2. The research turned out to be the fun part, and they want to show their
   working.
3. Tracing the maternal line back, they hit somebody **fully unique** — a
   person with no species and no precedent — and that is the moment the
   assignment stopped being homework. So the subject is Tuvix.
4. Their maternal grandmother was a **lower-decks Betazoid crewman aboard
   Voyager**, and she and Tuvix were together in the eighteen days he had.
5. Their mother is therefore three ways split — Talaxian, Vulcan, Betazoid —
   and came out supremely charismatic, deeply empathetic, and telepathically
   strong enough that the kid mentions it the way you mention a parent being
   tall. She never joined Starfleet.
6. The kid did. And — "it is a small galaxy" — they are now with one of
   **Tuvok's** descendants, which they find delightful and deliver as the
   punchline of the whole project.

What makes it land is that none of it is presented as tragedy. The kid is
pleased. The sadness is entirely the viewer's, arriving about four lines after
the kid has moved on, and it costs the writing nothing to produce.

Codes: `BOR-1` throughout, `UHP-1` on the punchline. **No `UHP+1` anywhere** —
that was the earlier draft's idea and the assignment framing replaces it.

The Starfleet half of point 6 is the tie to the rest of the shelf: this kid was
a friend of the pilot's, which is how the tape got aboard.

*One deliberate change from the brief, and it is overrulable in one word: the
Betazoid gift written here is* telepathy *rather than telekinesis, because the
Betazoid line is what the kid is explaining and empathy is the trait they are
proud of. Say the word and it goes back.*

**2. `TREK_TalentNight` — *Ten Forward Talent Night, stardate 44390.7*  [BUILT 2026-09-23]**

Somebody put a recorder on a table at the back of Ten Forward and forgot it.
Riker plays the trombone for nine minutes and is genuinely good for all of them;
the bar quietly starts serving again around minute seven. Data announces
eighteen stanzas to his cat and is not joking, and by stanza eighteen the room
is applauding and means it. Crusher taps on an unsprung deck and does not care.
Worf has declined to participate, is entered anyway, is extraordinary, and
declines to participate. An ensign does impressions of the senior staff, starts
on the captain, and finds out where the captain is sitting. Barclay is on the
list and not in the room. Then everybody leaves, nobody switches the camera off,
and two people stack chairs and argue about the trombone.

Forty-three lines, longest 57 characters. `BOR-1` throughout, `STS-0.2` twice,
`UHP-1` on the Worf silence and on the last line. **Not `MOR`** — see the note
in `tools/gen_tapes.py`: morale exists in `ISRadioInteractions` and no vanilla
recorded line uses it, so its sign is unproven and warmth is `UHP-1` instead.

Three things the writing settled, worth carrying to the rest of the shelf:

- **Riker plays the trombone, not the trumpet.** Rather than quietly correct
  the brief, the MC announces the trumpet, a voice off camera says "Trombone,"
  and the MC tries again. The joke is better than the fix and the fact ends up
  right, which is the shape to reach for whenever canon and a good line
  disagree.
- **Write around the quotable lines, not through them.** Data's poem is famous
  enough that transcribing it would be both a copyright question and a worse
  scene. What is on the tape is the *room's* reaction, stanza by stanza, which
  is funnier and is ours.
- **The camera is a character.** Half the tape is `note` lines — what the lens
  sees and nobody says — and that voice carries the comedy and the ending
  without anybody having to narrate. Every tape in the shelf can use it.

**3. `TREK_Meditation` — *Vulcan Guided Meditation for the Recently Bereaved (adepts' edition, abridged)***

Forty-one minutes, one voice, no music, no reassurance. It does not tell you it
will be all right. It asks you to name what you have lost, in order, out loud,
and then to put the list down where you can see it and leave it there.

Mechanically the most useful object in the shelf and deliberately so: `STS=0.05`
and `PAN=0` late in the tape, `UHP-1`. A player will watch this before going
out, which is exactly right — it is the thing the ship is for.

**4. `TREK_FieldRepair` — *Field Repair When Nobody Is Coming***

Six hours, recorded by a chief petty officer who has been shot at, tortured,
duplicated, replaced and back at work by lunchtime, and who has no theory to
offer. He holds the part up. He says what is wrong with it. He fixes it with
the wrong tool and explains why the right tool would not have been there.

`MEC+1`, `ELC+1`, `MTL+1` spread over the coded lines, and one or two
`RCP=` if there is a vanilla recipe worth the player's evening. The tape that
justifies the shelf to a player who does not care about any of this.

**5. `TREK_LeolaRoot` — *Ninety-Nine Things To Do With Leola Root***

The galley already stocks leola root stew. The presenter is relentlessly
cheerful and the root is relentlessly awful, and somewhere around thing sixty
he stops pretending and starts talking about the people he is cooking for and
how far away home is. Then he pulls himself together and gets on with thing
sixty-one.

`COO+1`, `BOR-1`, and one `UHP+1` for the part in the middle.

**6. `TREK_Ushaan` — *The Ushaan: Forms, Ice, and the Law of the Duel***

Andorian instructional, for the ushaan-tor already in the armoury. The
instructor is a magistrate rather than a fighter and spends the first ten
minutes on the paperwork, which turns out to be the point: the law is the
weapon and the blade is a formality. `SBA+1`.

**7. `TREK_Mokbara` — *Mok'bara, Taught Reluctantly***

A Klingon instructor who considers her students hopeless, says so at length,
and is not translated for any of it. For the bat'leth and the mek'leth.
`LBA+1`, and `SPE+1` on the two lines about the lirpa's reach.

**8. `TREK_Dilithium` — *Dilithium: Handling, Storage, and the Seventeen Ways It Kills You***

A safety film with a body count. Deadpan narrator, cheerful diagrams, one
dramatisation that goes on far too long and is clearly played by engineering
staff who were told they had to. It explains the machine the player is living
two squares away from, which is the first time anything in the mod has.

`ELC+1`, `BOR-1`.

**9. `TREK_Tribbles` — *Husbandry Module 12: Small Mammals, Rapid Breeders***

Opens as a competent animal-care film with good lighting and a presenter who
knows her subject. The last eleven minutes are the same room, from the same
camera, considerably fuller. `HUS+1`, `BOR-1`, and `PAN+5` on the last line.

**10. `TREK_Wolf359` — *Casualty list, read aloud***

Forty minutes of names. No music, no preamble, one reader who does not
editorialise and whose voice goes at about the two-thirds mark and comes back.

The heaviest thing in the shelf and the argument for the whole shelf: a mod set
in a world where everyone died has no business owning a Star Trek licence's
worth of optimism without also owning this. No skill codes at all. `UHP+2`,
`BOR-1`, and nothing else, because a tape that pays you to watch it is not what
this is.

**11. `TREK_Barclay` — *Holo-diaries (recovered; substantially deleted by order)***

A lieutenant's private recordings, most of them removed by somebody else before
the tape was filed, so it plays as fragments with gaps where the deletions
were. Funny for about ten lines — the man is bad at this and knows it — and then
quietly not, because what survived the deletion is the part about being lonely
in a crowd of four hundred people, and the deleted part was evidently the part
where he was happy.

`BOR-1`, `UHP+1`, and one `DOC+1` late on for reasons that only make sense if
you have met the Doctor. *(Stretch: it is the tape that reads best after the
EMH has been brought up, and the shelf has no way to know that yet — see
section 6.)*

### Tier 2 — found out in the world

These are genuine 1993 Earth tapes, seeded into vanilla loot tables the way
dilithium already is (`server/Items/TrekDilithium.lua` is the pattern). They
are the **outside view** of the mod's own ship, and they turn looting a town
into something that pays lore instead of bandages.

**12. `TREK_BackYard` — *AUGUST 11 — BACK YARD (DO NOT TAPE OVER)***

Somebody's camcorder. Nine seconds of a shape over the treeline, out of focus,
and then four minutes of a man explaining to his wife what he saw and getting
less sure of it as he goes, while she asks the questions a reasonable person
asks. He never gets angry. He just stops talking.

Houses. `BOR-1`, `UHP+1`, no skills. It is the player's own ship, before the
player got there — or it is not, and the tape has no opinion.

**13. `TREK_PawnShop` — *"SPACE JUNK — $40 AS IS"***

A pawnbroker's insurance inventory, walking the shelves with a shaky hand and
narrating prices. Twenty seconds in the middle he films something under the
counter glass and cannot describe its colour, gives up, and moves on to a box
of watches.

Pawn shops. Flavour first; there is an obvious hook into 1.5's contact store
later and it is deliberately not designed here.

**14. `TREK_NewsAtSix` — *KWLI NEWS AT SIX, [date unreadable]***

Local news taped off-air, mostly weather. Third item is a Fossoil night-shift
worker describing lights and a smell like a struck match, and being gently
laughed at by the anchor. The tape keeps rolling into the ad break, which is
the part that dates it and the part that is worth watching.

Bars, houses, the odd office. `BOR-1`.

### Tier 3 — the spine, gated on the campaign

These tie the shelf to `ROADMAP2.md`'s progression, and they are the reason the
shelf is worth doing before 1.6 rather than after.

**15. `TREK_FinalLog` — *SHUTTLECRAFT LOG, FINAL ENTRY — dubbed for playback***

**On the shelf from the start**, because a dead ship with one working screen is
precisely the situation this tape is about. It is the mod's premise, in the
voice of the person it happened to, and it is the whole of 1.6's cold start
delivered as a person rather than a tutorial pop-up.

What she says, in order:

1. **What she was doing here.** An observation posting: a pre-broadcast world so
   close to Earth's own twentieth century that the resemblance was the report.
   Watching from orbit, from a distance, the way this has always been done.
2. **The tapes.** She collected the television as an artifact and the tapes as
   an indulgence, and she is aware that this is not what the equipment was for.
3. **What happened.** Something else came. The aliens that attacked the world
   below destroyed the ship she came in, and she does not know much more about
   them than that.
4. **Where that leaves her.** The mothership is gone. Starfleet has no record
   that anyone was ever assigned here, so nobody is looking, and any rescue is
   years away at the very best.
5. **What is left.** This shuttle, and a dilithium reserve with a floor she can
   see coming.
6. **The question the whole game is built on**, and she asks it out loud like
   somebody who has just thought of it: *this world is a twin of Earth. Would
   there be dilithium down there?*

She does not answer it. The player does.

`BOR-1` only — **no XP**. Charging a tutorial in experience points cheapens the
tutorial and the tape, and this one is doing enough work already.

**16. `TREK_EarlierLog` — *SHUTTLECRAFT LOG, THE ENTRY BEFORE THE LAST***

Appears in the shelf **only once the ship is commissioned**. Recorded earlier
and therefore worse, because in it she still thinks she is going home, and
mentions twice what she is going to do first when she gets there.

`UHP+1`, `MOR+1`.

**17. `TREK_EnsignTape` — *(unlabelled; off a personal recorder)***

1.7's reward, taken from the downed ensign's pocket and worth more than the
crystal the roadmap was worried about awarding. Three minutes, recorded lying
down, breathing wrong. He is not sure anybody is coming and says so, and then
apologises for saying so, and then talks himself through his own field dressing
step by step because it is something to do with his voice.

`UHP+1`, `DOC+1`. `ROADMAP2.md` 1.7 wants a reward that is not another
crystal; this is it, and it costs the ship nothing.

### Stretch, and worth its own decision

**`TREK_Opera` — *Photons, Be Free: author's preferred cut (sixteen hours)***

Appears once the EMH has been brought up. It is not good. It is sincere, which
is worse. The tape is deliberately longer than any sane sitting — the joke is
that nobody will ever reach the end, and the codes are spread thinly enough
that finishing it is not a goal. Ties directly to a fixture that is already in
the cabin and does nothing narrative at all today.

**`TREK_Q` — *a tape nobody put there***

An unlabelled tape appears on the shelf some days after commissioning. No
explanation, in the shelf or anywhere else. It addresses "the current
occupant", finds the entire arrangement very funny, and knows one thing about
the ship that the player has not been told yet.

Mechanically this is the only tape that **arrives**: a one-shot server-side
placement into an existing container, persisted so it happens once. Note the
limit that shapes the writing — **a media line is static text and cannot
interpolate the character's name**, so the tape cannot address the player
personally. If that is wanted, it is an LCARS message from the ship, not a
tape.

---

## 6. What the shelf cannot do yet, and should not pretend to

The engine gives us a container of tapes and a television. It does not give us
a *library* — and three things on the list above want one:

- a tape that appears when the ship is commissioned;
- a tape that appears when the Doctor has been brought up;
- a tape that arrives on its own.

All three are the same small piece of server-side work: **a bounded record of
which tapes the ship has issued**, and a service pass that adds a tape to the
shelf when its condition is met and has not been met before. That is the
replicator's pattern store with one field, and it must not go in the ship state
that `Ship.commit()` transmits whole (*State that is transmitted whole cannot
hold a list that grows*) — though seventeen booleans is small enough that the
honest answer may be that it can, and the measurement is one sentence rather
than an argument.

**Until that exists, every tape is on the shelf from the first build.** That is
a perfectly good version one and it is the version to ship first: tier 1 and
tier 2 need nothing but text, an item and a shelf.

---

## 7. Tests

Extend what exists; do not add in-game checks (`DEV_GUIDE.md`, *Testing*).

`tests/test_assets.py`:

- every `RecMedia` entry's `category`, `itemDisplayName`, `title`, `subtitle`,
  `author`, `extra` and every line's `text` resolves to a key present in
  `Translate/EN/Recorded_Media.json` — and the reverse, so an orphaned key
  fails too. **Both sides need a floor** (*A check against an empty set is not
  a passing check*): fail if fewer than, say, ten tapes or two hundred lines
  come out of the file, or the pattern has stopped matching and everything
  passes against nothing;
- **no translation key is used by two different lines**, which is the trap in
  section 2 and the one failure here that is otherwise invisible;
- no `RecMedia` key collides with a vanilla one, and every one is `TREK_`
  prefixed;
- every `codes` token parses the way `ISRadioInteractions` parses it: longer
  than four characters, a three-letter code that exists in that file's
  `Interactions` table (or `RCP`), a legal operator, a number. A typo'd code is
  silently ignored by the engine, which is precisely why this check is worth
  more than it looks;
- every line's text is within the length band, so nothing sits on screen for
  half a minute;
- the tape item exists, names `MediaCategory = Trek-VHS`, and has a 64×64 icon
  on disk.

`tests/test_layout.py`:

- the shelf entry at 2,0 is `container = true`, its sprite really is a
  container in `tools/_catalog/tiles.json`, and the Lua matches the `.tbx` —
  all of which it already does for every other container;
- **2,0 is still standable**, which is the check that protects the armoury.
  This is new and it is the one the layout tests cannot currently express: the
  shelf's sprite must carry neither `solid` nor `solidtrans`.

`tests/test_multiplayer.py`:

- the shelf is built and stocked, reaching both clients with its contents;
- **every tape in it has media data**, read back off the item — the
  `B.stockReport` shape, and the check that catches a blank tape;
- `tests/pz_sim.lua` needs the rack's sprite in its list of container-bearing
  sprite substrings (`shop_generic`), or the rack is scenery in every test and
  every tape check fails on a feature that works (*The simulation has to be as
  unkind as the engine*, fault 4). **This bit on the swap**: nothing in
  `location_shop_generic_01_1` resembles any word already in that list, and
  removing the substring again is a mutation the tapes suite catches;
- and the simulation needs `RecordedMedia`, `register`, `addLine` and
  `setRecordedMediaData` stubbed **the way they really behave**: `register`
  returning something with `addLine`, and `getMediaData(id)` answering nil for
  an id nobody registered. A stub that accepts anything makes the media join
  untestable, which is the hole that let the empty lockers through twice.

**Mutation-check every one of them, one pass at a time**, and assert the
mutation applied.

---

## 8. In game

Not provable at the desk, in the order worth checking:

1. **A tape goes into the television and plays.** The one thing no static check
   can reach — whether a custom `MediaCategory` really is media type 1 in the
   running engine and whether `ISDeviceMediaAction` accepts it. Everything else
   here is downstream of this.
2. **The lines are readable and the pacing is bearable**, with a stopwatch on
   two long lines and two short ones, which is where the real length band comes
   from.
3. **The halos fire** — boredom, stress, XP — which is the `isOutside()` and
   ±5-tile question in section 2.
4. **The shelf looks right beside the screen**, with or without the monitor
   bank behind it. Render it and look.
5. **The tapes have their titles in the inventory**, which proves
   `setRecordedMediaData` landed. A row of tapes all called the same thing
   means it did not.
6. **The television needs power**: it runs on `TREK_Power.lua`'s own cell and
   `DeviceData.updateMediaPlaying` needs `isTurnedOn` and a volume above zero.
   A tape that plays in silence with no subtitles is the volume, not the tape.
7. **Two clients watching the same tape.** The engine claims to sync the
   current line; `ROADMAP.md` is right that this is exactly the kind of claim
   that wants checking.
8. **An existing save gets the shelf** on the next arrival after the
   `C.BuildRev` bump, stocked, because the container is new.

---

## 9. Open questions

- **Load order.** Vanilla's `ISRecordedMedia.lua` reads `RecMedia` on
  `OnInitRecordedMedia`, and the table is `RecMedia or {}` in both files, so a
  mod's shared Lua adding keys before that event fires is registered for free.
  Whether mod shared Lua is always loaded before the event fires has not been
  proven, and the cheap insurance is to register our own
  `OnInitRecordedMedia` handler that registers our tapes directly. **Do both.**
- **`spawning`**, the fourth argument to `register`, is an int 0-2 feeding
  `retailVhsSpawnTable` / `retailCdSpawnTable`. What 1 and 2 mean has not been
  read. Tier 1 and tier 3 are `0`; tier 2 wants either a value here or an
  ordinary distribution entry like dilithium's, and the distribution route is
  the one the mod already knows works.
- **Does a mod's `Recorded_Media.json` merge?** Every other translation
  category in this mod does, so this is expected rather than assumed — and it
  fails loudly if not (the key appears on screen).
- **The monitor bank at 2,0**: out, or layered. A look decides it.
- **Whether tier 2 tapes should be findable before the ship is**, which is a
  question about what the mod wants a new player's first hour to feel like and
  is the author's call.
- **Where the shelf's contents go if the cabin is ever refitted again.**
  `B.refitCabin` spills a deleted container onto the pad and moves the live
  `InventoryItem` rather than its id — which matters here more than anywhere,
  because a tape's identity is mod data on the item and recreating it from the
  type would hand the player a blank.

---

## 10. Order of work

1. ~~**One tape, end to end.**~~ **Built 2026-09-23.** `TREK_TalentNight`, the
   `Trek-VHS` category, the `TrekTape` item, the rack at 2,0, the stock pass
   with its read-back, and the checks. `tools/gen_tapes.py` is the source of
   truth for every tape and writes both files that have to agree, so the
   duplicate-key trap in section 2 is **designed out rather than tested for**:
   a line's key is derived from its tape id and index and a collision is not
   expressible.

   Four mutations were run one at a time and all four were caught: dropping the
   `setRecordedMediaData` call (a shelf of blank tapes), a tape id naming a
   recording nobody registered, a malformed effect code, and a container count
   that no longer matches the layout. Two gaps in the harness came out of it,
   both the shape `DEV_GUIDE.md` keeps meeting — `tests/pz_sim.lua` had no
   radio at all, and its item stub could not express a tape with no recording
   on it, which is the one failure that matters here.

   **Still unproven, and it is the whole of section 8:** none of this has been
   in a game. The count checks in the tapes suite are also thin while there is
   only one tape — `labelled == len(ids)` cannot tell much about a list of one
   — so they get sharper with the second tape rather than needing rework.
2. **The shelf and the item settled** — the `.tbx` change, the icon vetted
   against the set, the plan looked at.
3. **Tier 1**, written. The writing is the work; the machinery is done after
   step 1.
4. **Tier 2**, plus a distribution entry, which needs a fresh world to see.
5. **The issue record** (section 6), which unlocks tier 3's gating and the
   arriving tape.
6. **Tier 3**, alongside 1.6 and 1.7, because two of the three tapes are those
   milestones' own voices.

Step 1 is one evening and it answers the only question that can sink the
feature.
