# Lore — the tape shelf

The plan for telling stories aboard this ship, and the engine research it rests
on.

`ROADMAP.md` and `ROADMAP2.md` say what the ship *does*. This file says what it
**remembers**. Everything here is delivered through one fitting — a small shelf
beside the television in the bow — and a set of VHS tapes on it, each of which
is a piece of somebody's testimony.

`COMMS.md` is this file's companion and holds what is still **talking** — the
channel to the *Adirondack*, and the trigger engine that section 6 parks.

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

**The pilot is Lieutenant Lucy Shepard**, cultural survey specialist off the
**U.S.S. Adirondack** — a science ship about Voyager's size, a hundred and
forty-one crew. She is a historian by temperament and privately a buff:
Starfleet history, and family histories above all. That is the entire reason
the shelf exists — the tapes are *her collection*, not the ship's library, and
it is why the bow of a shuttle has a row of somebody's favourite recordings in
it.

**The cabin is hers, and that is the retcon that pays for the whole mod.**
Every vanilla object in this ship — the fridge, the oven, the counters, the
theatre chair, the lamp, the lockers, the television — had no in-fiction reason
to be aboard a Starfleet shuttle, and now it has one: **she collected them.**
A survey specialist furnished her field station with what she was studying,
because you cannot understand a people from orbit. Her department calls it
method; the *Adirondack* called it clutter. One tape, and twenty-four squares
of borrowed Project Zomboid furniture stop being a compromise and become a
character trait.

**The medium follows from the machine.** She dubbed her favourites down onto
magnetic tape because that is what the television takes — videos, holos
flattened to two dimensions, and transcripts read aloud. That last one matters
more than it looks: it is the in-fiction licence for a tape that is nothing but
a voice reading, which is what several of the best ideas in the library are.

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

**The world is a made thing, and its maker is not the villain.** Kentucky is a
copy. It was an act of grief rather than an experiment, the thing that made it
has been dead of old age for three centuries, and the towns on the map grew
there by themselves. Who made it, how, and why the names are what they are is
**1c** — and it is deliberately *not* the same story as the plague. **The origin
of the world and the origin of the virus are unrelated, and that is the point:**
the Changeling did not build this place. It found it, for the same reason
Shepard did.

### What the framing buys

It explains the medium, it explains why the tapes are *in the room* rather than
in a menu, it lets the shelf hold genuine 1993 Earth tapes alongside Starfleet
ones without a seam — and it gives the collection an owner, which is the thing
that turns a list of stories into somebody's shelf.

---

## 1b. The arc: what actually happened here

Settled 2026-09-23. This is the spine the ship's logs deliver, in order, and
the reveal at the end of it is the mod's answer to what the Knox Event *was*.

**The posting.** Shepard's detachment is parked at a hidden outpost above a
world so close to Earth's own 1990s that the first survey logged it as a sensor
fault. No relay, no traffic, nothing filed — deniable by design. She beams down
at dawn and up before dark, six months of market days and radio broadcasts, and
she is going to get a very good paper out of it.

### The timeline, and why it is shaped like this

**Shepard's last entry is the player's first day.** Project Zomboid starts on
**9 July 1993** (`StartMonth 7`, `StartDay 9`), and entry six is recorded that
morning: she beams up, and hours later somebody who has never heard of Starfleet
wakes up in Knox County.

Getting there forced one decision, and it improved the story. **The sabotage and
the release are five months apart.**

| entry | day | date | |
|---|---|---|---|
| — | — | **9 Feb 1993** | the *Adirondack* is disabled from the inside |
| one | 2 | 10 Feb | stranded above a world having an ordinary week |
| two | 19 | 27 Feb | contact; she stays for the fieldwork |
| three | 141 | 29 Jun | the county dies in two days — and she connects it to February |
| four | 146 | 4 Jul | the Doctor's science |
| five | 149 | 7 Jul | nobody is coming; Section 31 denies it |
| six | 151 | **9 Jul** | the truth, the chair, she beams up — **gameplay day 1** |

The gap is not a workaround. A careful operator does not blind the witnesses in
the same week it runs the test; it clears the room, prepares, and comes back.
Three things fall out of it:

- **Entry one is worse in the good way.** She is sabotaged, stranded and
  looking down at a perfectly healthy planet. The markets open. The radio
  plays. A player standing in July reads a February tape saying nothing is
  wrong, and does that arithmetic themselves.
- **Entry three gains its best beat** — the moment she realises the two events
  are one operation. *"We were never the target. We were the witnesses. They
  blinded us and went away."*
- **Entry five's best line becomes literally true.** "Five months angry at the
  wrong people" is February to July, exactly.

And it gives the rescue feature its number: **eleven of the crew stayed on the
ground for the work**, which is why there are Starfleet survivors scattered
across a dead county. They stayed for the science and the science killed them.

**The break.** On the ninth of February the *Adirondack* is damaged and **cannot
depart**. Not destroyed and not lost: she is intact, crewed and fed, with warp
and impulse gone — a very expensive orbital platform. Some of the crew were
on the surface when it happened, and eleven of them chose to stay.
Starfleet does not know anyone was ever here, and long-range comms have been
dark the whole time, so nobody is looking and no rescue is coming.

**The ship can still transport, and that is the mechanic.** Every survivor the
player beams to safety goes *up there* — which is where `ROADMAP2.md` 1.7's
"safe off-screen recovery" has always needed to be going. **Every ensign
rescued is one of her crew**, off a number the player has already heard.

**The wrong answer.** Shepard reasons her way to **Section 31**: a hidden
outpost, a Federation bioweapon precedent, and a plague. It is honestly argued
and it is wrong, and it has to be written that way — a misdirection that is a
lie is cheap, and a misdirection the audience can out-reason is worse.

**The truth**, and it lands in the last log. A **Changeling** left the Great
Link deliberately, carrying knowledge of the morphogenic virus Section 31 used
against its own people. Working alone, in isolation, it spent decades turning
that into something else. Nearly sixty years later it found this outpost — and
the near-perfect copy of a human world underneath it — and decided that was the
ideal proving ground.

**It did not make this world, and that matters.** The origin of the plague and
the origin of the planet are unrelated stories (1c). The Changeling found the
place exactly the way Shepard did, and for exactly the same reason: no relay, no
traffic, nothing filed, deniable by design, and an order on the file saying
nobody may interfere. **The Prime Directive is what left it undefended.**

**Why this world.** It is a full-scale working model of Earth that developed
independently to a 1990s baseline — a control group rather than a replica. Same
biology, same densities, same infrastructure. The Changeling is not testing a
weapon on strangers; it is **rehearsing on a copy of the homeworld of the people
who tried to exterminate its species**, and what comes after Kentucky is the
Federation worlds.

**How the weapon works, and why the Doctor cannot read it.** It is a graft. The
Founders' morphogenic virus attacks what a body is made of; **Borg nanoprobes**
rebuild a dead one and keep it running — canon revived Neelix eighteen hours
dead with them (VOY "Mortal Coil"). Bolted together they produce a corpse
reassembled to a template and animated, with **no Queen, no Collective and no
purpose.** Which is the mod's thesis in one line:

> **A horde is a Collective with no Queen.**

It is also why entry four works. The Doctor finds *confusing* Changeling markers
because he is reading half a signature — *"I can support the chemistry. I cannot
support the author"* is literally true, because there are two.

**Where the parts came from.** Neither half had to be invented. Daystrom
Station's vault, as inventoried in *Picard*, holds **the morphogenic virus
itself** alongside a Borg vinculum and a Queen's remains — both halves of this
weapon, in one Federation warehouse. What this took was not a laboratory so much
as a burglary. *(Available and stronger if wanted: Section 31's Project Proteus
tortured ten Founder prisoners in the mid-2370s to build changelings that could
defeat blood screening. A survivor of that programme has first-hand knowledge of
Federation bioweapon work because it was the specimen.)*

**And there is a cure in the archive that nobody has read.** In 2153 Phlox
synthesised a working counter to Borg nanoprobes using **omicron radiation** and
filed it in a medical log canon then ignored for two hundred and fifty years
(ENT "Regeneration"). It is not a miracle; it is paperwork. Which makes it
exactly the right job for a hologram whose defining trait is that he reads
everything.

So the apocalypse the player is surviving is a **reply**. The Federation
attempted a genocide, and two generations later the survivor of it is running
the experiment on a world full of people who have never heard of any of them.
The player is standing in the consequence of an argument Trek never settled,
which is the shelf's whole thesis in one move.

**And the two griefs rhyme, which is the spine.** A Douwd built this county
because it could not bear one death; a Changeling is emptying it because it
cannot bear a genocide. The world was made by grief and is being unmade by
grief, and both makers are the last of something.

### The logs, as a series

Six entries, settled 2026-09-23. Each is a different kind of tape, and the
misdirection is broken from the inside rather than by Shepard out-reasoning it.

| | | |
|---|---|---|
| **One** | *Field Station* | **BUILT.** The posting, the world, the cabin, the tapes, the break, the scattered crew. Plants Section 31 without naming it. |
| **Two** | *Somebody Answered* | **BUILT.** She accuses Section 31 outright, with no evidence and an honest admission of that. Then she raises the *Adirondack*: intact, crewed, fed, and going nowhere — warp and impulse gone. **They can still transport.** They ask her to come up; she refuses, because she is the only one of them who knows how this century boils water. |
| **Three** | *The Attack* | **BUILT.** The event itself, in detail: the *Adirondack* disabled first, then the region below collapsing far faster than any plague she knows of. |
| **Four** | *What the Doctor Found* | **BUILT.** She and the **EMH** run the science. Confusing Changeling markers, which they both read as Section 31 tradecraft. |
| **Five** | *Nobody Is Coming* | **BUILT.** Long-range comms have been dark the whole time; there is little chance of rescue. The crew argue about isolating somewhere on the ground and whether that breaks the Prime Directive. Shepard stays. Then **the Section 31 officer aboard** says the attack blindsided them too, and they have no idea where it came from. |
| **Six** | *The One Who Left the Link* | **BUILT.** Somebody aboard works out the truth — a rogue Changeling, building on the Founders' own virus — and tells her. Shepard beams up. |

**All six are written as of 2026-09-23**, and three details of the execution are
worth keeping because they are reusable:

- **The science is right and only the attribution is wrong.** In entry four the
  Doctor states the chemistry and then refuses the conclusion — "I can support
  the chemistry. I cannot support the author." She overrules him. The tape
  therefore contains its own correction, and a second viewing finds it.
- **The misdirection is broken by the accused, not by the detective.** Entry
  five's Section 31 officer denies it credibly because they had every reason to
  lie and did not bother: *"No. But then I would not be calling you."* That
  leaves Shepard with something worse than a villain — an absence.
- **The reason she leaves is a moved chair.** Entry six: nothing broken,
  nothing taken, a chair in a different place. That is the theatre chair at 1,2
  the player sits in to watch these tapes.

Three things that structure settles, and they are worth more than the plot:

- **Shepard is alive.** She ends entry six aboard the *Adirondack*, which is why
  the player inherits a working shuttle with somebody's furniture in it rather
  than a derelict with a body in it.
- **The accusation is broken by the accused.** Section 31 is aboard, and the
  officer's denial in entry five is credible precisely because they had every
  reason to lie and didn't. That is a far better way out of a misdirection than
  the detective spotting a flaw in her own logic.
- **The EMH earns a plot.** Entry four puts the sick bay's hologram into the
  investigation, which makes a fixture the player already talks to part of the
  story rather than a utility.

**Mechanically they all sit in the rack from the first arrival, and that is a
deliberate decision (2026-09-23), not an oversight.** Getting the ink on the
page beats building the machinery to ration it, and a reveal that is merely
*available* early is a far smaller problem than a reveal that is never written.
The gating design in section 6 stays parked until every log exists — and when it
is wanted, the answer is probably **a survivor hands you the next log**, which
solves `ROADMAP2.md` 1.7's reward problem at the same time: the reward for a
rescue is a piece of the truth, which costs the ship nothing and is worth more
than a crystal.

---

## 1c. Where the world came from

Settled 2026-09-24. This is the deep history, and the mod's answer to the
question a player asks in their first ten minutes: *why is there a Kentucky?*

**A Douwd made it, and his name is Tucker Gold.** See *Tucker Gold, and how
anybody finds out* below before writing anything that references him — the name
is the design's, not the fiction's, and no character knows it at the start.

Canon has met a **different** one: **Kevin Uxbridge**, TNG "The Survivors"
(2366). He is the precedent and nothing else — another of the same kind, on
another planet, whose case is on file and whose file is the only reason anybody
here has a word for what they are looking at. Rana IV's surface had been scorched to bare rock and all eleven thousand
colonists were dead — except for one intact patch of land with a house, a garden
and two people in it. Kevin, and a wife who had died in the attack and whom he
was still maintaining. He describes himself as *a being of disguises and false
surroundings*. He is a pacifist who had never harmed anything, and in a single
instant of grief he erased the **Husnock — fifty billion beings, everywhere, at
once.** Picard declines to arrest him: *"We have no law to fit your crime."*

That episode is this mod's origin story at one-house scale. Everything below is
the same act performed larger, by somebody else of the same kind.

**What happened here.**

1. A Douwd passing through Earth in the **1690s** falls in love with a
   middle-aged human in the Ohio country. Its species is not supposed to be able
   to do that.
2. Real history takes her. The valley was being emptied in those decades by
   raids driven by a fur trade conducted hundreds of miles away: she dies in a
   war over beaver pelts, fought by people she never met.
3. It cannot cope. So it copies the **land** and the **people on it** to a world
   in a similar orbit — the river's exact bend, the falls in the same place, the
   escarpment, the salt licks, the hunting country, and **her.**
4. Then it does the thing Kevin Uxbridge did not do. Kevin kept a projection and
   stayed a god. **This one put its power down**, made itself an ordinary human,
   and the two of them grew old together and died.
5. The world was left alone for roughly **three hundred years**, and grew.
6. Starfleet found it.

### Tucker Gold, and how anybody finds out

Settled 2026-09-24.

**The Douwd who made this world is not Kevin Uxbridge.** This one lived here,
under a human name, and the name is **Tucker Gold** — the name he chose when he
stopped being what he was, which is the only name he has and the reason he has
one at all.

**Nobody in the fiction knows that at the start, and Shepard never learns it
before she goes up.** Her six logs are recorded by a woman with a Douwd precedent
in her archive and a hypothesis she cannot test. The truth arrives *after* her
last entry — which means **it arrives through the player**, and that is the whole
reason the clue chain exists rather than a twelfth tape.

**Starfleet's answer is that a Q did it, and Starfleet is wrong. There is no Q in
this mod.** The suspicion is on the file because it is the only category the
Federation has for *a planet that was not there before*: honestly argued, widely
held, and false. That makes it the **second misdirection**, and the same shape as
the first — Section 31 is out-reasoned by the accused (1b entry five), and the Q
theory is out-reasoned by the evidence. Neither is a lie, and neither survives
what the player digs up. Write the suspicion as respectable, because everyone
sensible holds it.

### The clue chain: six fragments, and a conversion

**Built 2026-09-24.** The six tapes are `TREK_GoldOne`..`TREK_GoldSix` in
`tools/gen_tapes.py`, in the `tucker` voice (the fragment's own cyan); the items
are `TrekShuttle.TrekFragment1`..`6` from `tools/gen_fragment.py`; the machinery
is `COMMS.md` 9. His name is spoken in fragment five, where he takes it; six is
to whoever found it. A fragment lost is found again by a later probe -- *he made
more than one copy of everything* -- so the chain cannot be soft-locked.

**Tucker Gold left holo recordings.** A being that spent an immortal life copying
and preserving things, and then made itself mortal, leaves records the way a
mortal leaves letters. They are scattered across the county because he lived a
whole human life across it.

The loop reuses three systems that exist and adds one:

1. **A probe finds a site.** `PROBES.md`'s sweep gains a third result alongside a
   crystal and a survivor: **a clue.**
2. **The player recovers a fragment** — an item, at the site.
3. **Shepard converts it.** *"Hang on. I can put that on magnetic tape."* A comms
   beat (`COMMS.md`), and the only place in the mod where the channel hands the
   player an object.
4. **A new tape appears in the shelf.**

Which is why the medium was always going to hold: **1a already established that
she dubs holos flattened to two dimensions onto tape**, because that is what the
television takes. The licence was written a day before the feature needed it, and
that is the strongest sign the framing was right.

**Six fragments, mirroring the six logs.** Six recordings from the woman who
survived this, and six from the man who built the place she survived it in. The
symmetry is the reason for the number.

| | |
|---|---|
| **One** | what he was. Non-corporeal, passing through, and curious about a species that dies. |
| **Two** | her. And the thing his kind is not supposed to be able to do. |
| **Three** | her death, and the war over pelts that caused it. |
| **Four** | the copy — the land, the river, the hunting country — and the admission that he copied **people**, and what he thinks he owes them. |
| **Five** | putting the power down. What it cost, and whether he ever told her she had died. |
| **Six** | an old man, dying, recording for whoever eventually asks, because he knew the world would outlive them both. |

**Fragment six is addressed to the player** — not by name (a media line is static
text and cannot interpolate; see 5) but to *whoever found this*. It is what the
`TREK_Q` stretch idea was reaching for, and Tucker has a better claim on it than
a joke does. `TREK_Q` is **retired**: there is no Q.

**And a fragment is losable until it is converted.** It is an item; it stays on a
body like everything else. Once Shepard has put it on tape it is shared,
permanent, and on the shelf for everyone — which makes the conversion the thing
the player is actually racing to, and gives the channel a reason to be urgent.

### Dilithium in his ground

Settled 2026-09-24, by the author, when the first cold-start play went a long
way without finding a crystal. **The copying left dilithium in the land.** It
lies on the wild ground of the county, in the fields and the woods, and never
in the towns, because the towns grew on top of it afterwards and were never his
work. That is the whole of the mechanism, and it is `server/TREK/TREK_Wild.lua`.

**Nobody in the fiction knows why.** It is a fact about the county the crew can
use and cannot explain: the crystal's own tooltip says only that they turn up in
wild ground and never in town. It is one more discrepancy in the file, of the
kind 1c licenses, and the fragments are where it could be answered. Nothing
written so far answers it, and nothing has to.

### The towns grew, and that is the whole finding

**Nothing after step 3 was designed.** The Douwd copied a river valley in the
1690s and there was no Louisville in it — European settlement of Kentucky starts
in the 1770s. Every town on the map arrived on its own, in the three centuries
the world spent unattended.

**So the names are a coincidence and will be read as one. They happened to call
it Kentucky too.** That is not a shrug, it is the report. Put a town where the
boats have to stop and somebody will put a town where the boats have to stop. The
map is near-identical in the ways that follow from the terrain and quietly wrong
in a hundred ways that do not — which is exactly what a cultural survey
specialist would kill to be looking at, and which is free licence for every
discrepancy a player ever notices. **A wrong street name is canon.**

What Starfleet files it as: **Hodgkin's Law of Parallel Planetary Development,
observed under laboratory conditions** — because somebody accidentally built the
laboratory. Which is also why the order is *do not touch it.*

### The two precedents that make "observe only" defensible

The mod needs that order to be honestly arguable rather than bureaucratic
cowardice, because it is the order that left the world undefended. Canon supplies
two.

- **Miri** (TOS, 2266). A planet with Earth's continents and Earth's cities.
  Kirk: *"Earth... but it can't be."* **Never explained, by anybody, ever.** So
  Starfleet has a filing category for this and exactly one prior entry in it.
- **The Uxbridge determination** (2366). A captain found a Douwd's fabrication
  with a resurrected woman living inside it, and **walked away and left it
  running.** Seventy-two years before the mod's present, the Federation
  established on the record that it does not interfere with these and does not
  judge them.

Together they turn the posting into case law. Shepard's file reads *parallel
development, cf. the Miri anomaly, non-interference per Uxbridge, recommend
observation only.* Every word of it is true, correctly reasoned, and the reason
everyone died.

### The clock, and why it is never explained

| | |
|---|---|
| the mod's present | **2435** — `NOW_YEAR` in `tools/gen_tapes.py`, and pinned by the arc rather than chosen |
| the world's present | **1993** — `StartMonth 7`, `StartDay 9` |
| the gap | **442 years** |

**Take the year from the generator, not from here.** `gen_tapes.py` pins
`NOW_YEAR = 2435` with its reasoning attached — Section 31 deployed the Founder
virus around 2375, the Changeling worked in isolation for nearly sixty years —
and it has already caught one dating error in a built tape. A date in a prose
document is not a thing anybody checks; a date in the generator is.

A copy that runs at Earth's rate cannot lag, so a world copied in the 1690s and
left alone ought to read 2435 today rather than 1993. **The mod does not resolve
this and must not try.** Shepard notices it, checks it four times and cannot
account for it, which is in character for a historian and costs nothing: *their
calendar says 1993, mine says 2435, and nobody ever explained Miri either.* Put
no external build date in any tape. Non-corporeal immortals do not file
timestamps.

### One line to hold, and one to decline

**Hold this: the place is manufactured and every person on it is real.**
Trelane's father, about the humans his son had been playing with — *"They're
beings, Trelane. They have spirit. They're superior."* The moment Kentucky's
population is set dressing, the mod is a shooting gallery and the shelf is
decoration. The fabrication is the shelf the world sits on, not the world. It
also protects the thing the framing is for: a player imagining themselves a
native of this county is imagining a real person, from a real town, with real
parents.

**Decline this:** naming the woman's nation and making a specific people's
catastrophe the mod's plot machinery. Keep the place specific and the person
private — the only record is a name on a headstone somewhere in the county, and
no tape ever finds out more than that. Voyager's own history is the cautionary
case: that series' Native American consultant had been publicly exposed as a
fraud nine years before he was hired to vet Chakotay, which is why Chakotay has
no named nation to this day.

---

## 1d. The three lines

Settled 2026-09-24. The death screen is the mod's cheapest and most-seen piece
of writing, and it replaces the game's own triad:

> **M-class. Earth-like. Unprotected.**
> **Observe, report and explain.**
> **This was your away mission.**

**Unprotected** is the indictment and **explain** is the order nobody could carry
out. The player reads their own orders every time they die.

*Parked and still available: showing vanilla's lines until the ship is found and
switching to these afterwards, so the reframe lands at commissioning rather than
at first death. It needs the issue record (6, `COMMS.md`) and is not worth
blocking the triad on.*

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
  0 TVLA        0,0 monitor wall   1,0 television on a low table
  1 F*.p        2,0 tape shelf     3,0 armoury
  2 oh.M
  3 wD.H
  4 m*.B
  5 R.@B
```

**The shelf is at 2,0: `furniture_shelving_01_28`, a metal wall shelf.**

```
ContainerCapacity 30    container metal_shelves    MoveType WallObject
Facing S    attachedN    ContainerPosition High
(no `solid`, no `solidtrans`)
```

It is the sprite `DEV_GUIDE.md` already lists under *Half the tileset does not
block its square*, and `Facing S` / `attachedN` is the orientation the bow's
monitor banks use — it hangs on the forward bulkhead and **2,0 is still deck**.

That last part is the whole reason for the choice: **2,0 is the only square a
player can stand on to open the armoury at 3,0**, because 3,1 and 3,2 are the
other two lockers. A floor-standing container here leaves the ship's sidearms,
blades and uniforms reachable diagonally at best.

### A video-shop rack was tried here, and reverted

Worth recording, because the failure is a new one for this project.
`location_shop_generic_01_1` is catalogued as **"Comics Shop Shelves"**,
capacity 20, `container = shelves`, `Facing S` — everything a tape rack should
be, on paper. In the game it draws as a **grocery shelf stocked with orange
soda**, at twice the depth a twenty-four square cabin can spare.

Nothing in `tiles.json` says so, and nothing in it could: `CustomName`,
`GroupName` and `container` describe what a tile is *for*. **None of them
describes what it looks like.** So a fitting chosen for its silhouette is in the
same category as a mesh — it has to be looked at, and the catalogue is not a
substitute for looking. That is *Render it and look* arriving from the one
direction this project had not met it from, since a tile cannot be put through
`tools/preview_model.py` at all.

The genuine video-rental racks are in the tileset —
`location_entertainment_theatre_01_120..135`, groups literally named "Large
Rental" and "Small Rental" — and every one of them is a **two-tile** piece
(`SpriteGridPos 0,0` + `1,0`), as are both magazine shelves. The bow row has no
two adjacent free squares: 1,0 is the television and 3,0 is the armoury. The
Fossoil magazine shelf is the near miss worth remembering — two tiles, but
**non-blocking**, and from the same tileset as the cabin's own walls.

The monitor bank that used to be on 2,0 is **gone and has not come back**: two
wall-mounted objects on one edge of one square is the thing that looks like a
bug whether or not it is one. The bow is three screens and a shelf.

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
honestly. It is plain XML: a `<furniture>` block holding the shelving
set's four facings (appended, so its document index is 33, which is what
`<object FurnitureTiles="33">` means — `tools/import_tbx_layout.py` builds its
table from `root.findall("furniture")` in document order), `33` added to
`<used_furniture>` to keep that list a permutation of the block indices, and the
object at 2,0 repointed from block 1 to block 33. `orient` names the wall the
object stands against, so each slot takes the tile whose own `attached<Edge>`
property matches — `orient="N"` on the bow bulkhead resolves to
`furniture_shelving_01_28`.

`tools/import_tbx_layout.py` reads it back as `2,0 furniture_shelving_01_28
container=metal_shelves` and `tests/test_layout.py`'s drift check passes both
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

Twenty-one tapes in three tiers, plus two stretch. Ids are readable rather than
GUIDs (vanilla's
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
6. The kid did. And — "it is a small galaxy" — their closest friend at the
   Academy is one of **Tuvok's** great-grandchildren, which they find
   delightful and deliver as the punchline of the whole project. **Friends,
   not a romance** (decided 2026-09-23), and the punchline is better for it:
   half of Tuvix *was* Tuvok, so the two of them worked out on a padd that
   they are cousins, sort of, and there is no form for that.

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

**One canon fact worth using, and the ship already has the character for it.**
The EMH *refused to perform the separation on ethical grounds* — Janeway did it
herself. The Doctor is the franchise's only on-record conscientious objector to
Tuvix's death, and this ship has an EMH as a fixture who already earns a plot in
1b's entry four. If anything in the mod ever reacts to this tape, it is him.

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

**And the list can be invented, which is the licence nobody expects.** The
production deliberately never fixed the roster so that later episodes could add
ships: only three hulls were ever named in script — *Melbourne*, *Kyushu*,
*Chekov* — out of thirty-nine lost from forty, with nearly eleven thousand dead.
Every other name on this tape can be ours and still be canon-correct.

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

**Superseded in part (2026-09-24).** #15 and #16 below were written before the
arc in 1b was settled, and #15 contradicts it -- it has her ship destroyed and the
mothership gone, where 1b has the *Adirondack* intact and able to transport. The
six built logs (`TREK_LogOne`..`LogSix`) are what these two became, and neither
is to be written. **#17 is built**, as `TREK_EnsignLog`, issued to the ship on the
first rescue (`COMMS.md` 9). They are kept below as the record of the idea.

These tie the shelf to `ROADMAP2.md`'s progression, and they are the reason the
shelf is worth doing before 1.6 rather than after.

**15. `TREK_FinalLog` — *SHUTTLECRAFT LOG, FINAL ENTRY — dubbed for playback*** — SUPERSEDED by the six logs

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

**16. `TREK_EarlierLog` — *SHUTTLECRAFT LOG, THE ENTRY BEFORE THE LAST*** — SUPERSEDED by the six logs

Appears in the shelf **only once the ship is commissioned**. Recorded earlier
and therefore worse, because in it she still thinks she is going home, and
mentions twice what she is going to do first when she gets there.

`UHP+1`, `MOR+1`.

**17. `TREK_EnsignTape` — *(unlabelled; off a personal recorder)*** — BUILT as `TREK_EnsignLog`

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

**`TREK_Q` — RETIRED 2026-09-24**

There is no Q (1c). The suspicion that one made this planet is Starfleet's, it is
honestly held, and it is wrong — which makes it a misdirection rather than a
character, and misdirections do not get tapes of their own.

**What it was reaching for now belongs to Tucker Gold.** An unlabelled tape that
addresses "the current occupant", finds the arrangement remarkable, and knows one
thing about this world the player has not been told: that is fragment six, and a
dying man has a better claim on it than a joke did. The one mechanical note worth
keeping from this entry is still true and still the constraint — **a media line is
static text and cannot interpolate the character's name**, so the fragment
addresses *whoever found this*, never the player personally.

---

## 6. What the shelf cannot do yet, and should not pretend to

**Built 2026-09-24, as `COMMS.md` 9 describes.** The issue record exists: the
channel issues a tape (`TREK_CommsServer.issueTape`), and `TREK_Build.deliverTapes`
puts it on the shelf the next time the cabin loads, in existing saves too. A tape
`gen_tapes.py` marks `issued` is registered and not stocked. Its customers so far
are the first rescue (`TREK_EnsignLog`) and the six Tucker Gold fragments
(`TREK_GoldOne`..`Six`). The logs are still all on the shelf from the first build,
which 1b decided and nothing here changes. What follows is the design as it stood.

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

**And the record now has a second customer, which is how it gets built.**
`COMMS.md` specs an interactive channel to the *Adirondack*, and its trigger
engine is this same object — one bounded server-side record of what this ship has
fired, calls and tapes in one table, and one slow service pass. That feature pays
for 10's step 5 rather than waiting on it, so the gating design here is parked
*until comms needs it* rather than parked indefinitely.

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
- `tests/pz_sim.lua` needs the shelf's sprite covered by its list of
  container-bearing sprite substrings, or the shelf is scenery in every test and
  every tape check fails on a feature that works (*The simulation has to be as
  unkind as the engine*, fault 4). `shelving` covers the wall shelf; the video
  rack needed `shop_generic` added, and **this bit on the swap in both
  directions** — the substring went in with the rack and came out with it, and
  either way round the tapes suite catches it;
- and the simulation needs `RecordedMedia`, `register`, `addLine` and
  `setRecordedMediaData` stubbed **the way they really behave**: `register`
  returning something with `addLine`, and `getMediaData(id)` answering nil for
  an id nobody registered. A stub that accepts anything makes the media join
  untestable, which is the hole that let the empty lockers through twice.

**Mutation-check every one of them, one pass at a time**, and assert the
mutation applied.

---

## 8. In game  **[CONFIRMED WORKING 2026-09-23]**

**The shelf, the tapes and the television all work, tested repeatedly by the
author.** A tape goes into the cabin's television and plays.

That settles the one thing no static check in this repository could reach: a
**custom `MediaCategory` really is media type 1 in the running engine**. So
`RecordedMedia.getMediaTypeForCategory` returning 1 for every string that is not
`"cds"` is confirmed behaviour rather than bytecode reading, and everything in
section 2 now stands on an observation.

It also settles, by implication, three joins that each fail silently:

- **the mod's own `Recorded_Media.json` merges** into the engine's translation
  table -- a tape playing readable English rather than `RM_TREK_...` keys is the
  proof;
- **`OnInitRecordedMedia` reaches a mod's `RecMedia` entries**, by whichever of
  the two routes got there first (vanilla's walk, or our own handler);
- **`setRecordedMediaData` lands on the authority**, because a tape carrying no
  recording would have gone into the television and done nothing.

### A correction worth keeping

For several turns this file, and the assistant writing it, repeated that "the
television has never been switched on in a real game" -- sourced from
`ROADMAP.md`'s *Not yet seen in game* list and `DEV_GUIDE.md`'s current-state
section. **Both were stale.** The author had tested the television many times.

That is this project's own rule arriving from a new direction: *A test encodes
an expectation, not a fact* applies to a **document** just as hard. A
"not yet proven" list is a claim about what somebody had got round to writing
down, and it decays silently every time the game is played and the file is not
edited. Both lists are corrected now. **When a doc says something is unproven,
that is a prompt to ask, not a fact to repeat at the person who has played it.**

### Still genuinely unobserved

Narrower than the list that used to be here, and none of it blocks anything:

1. **Whether the line effects fire** -- the boredom, stress and unhappiness
   halos. Those are `ISRadioInteractions` reaching the player through
   `OnDeviceText`, and they depend on the +/-5 tile range check and on the
   source square and the player square agreeing about `isOutside()`. The cabin
   is not a building, so they should agree; that is reasoning, not evidence.
2. **Two clients watching one tape.** The engine transmits the current line with
   the device state, so this should need nothing of ours -- which is exactly the
   kind of claim `ROADMAP.md` says wants checking.
3. **The pacing over a long tape**, now that entries run to forty-odd lines.
4. **An existing save** picking the shelf up on the refit at revision 27.

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

**Step 5 now belongs to `COMMS.md`.** The issue record is that feature's trigger
engine as well as this one's gating, so it gets built there — which means the
order above can run 1 → 4 without it, and tier 3's gating and every converted
fragment arrive as a side effect of the channel rather than as work of their own.
**Both are built** (2026-09-24): the issue record, the ensign's tape and all six
fragments.

**And 1c is the writing brief a new session needs.** The world's origin, the
precedents, the clock and the two rules to hold are settled; what is *not*
written is any tape that carries them. `TREK_Uxbridge` is the one that does most
of the work, and it needs no machinery that does not already exist.
