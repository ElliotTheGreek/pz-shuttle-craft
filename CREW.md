# CREW.md — the people aboard the U.S.S. Adirondack

The Adirondack is crewed. Starfleet officers and crew of several species step out
of the turbolifts and walk her decks. They take their posts, sit down, and talk
to each other and to you, then leave again by the lifts. This file covers who
they are, what they know, and how their talk is written and run.

- **§1** what they are in the engine
- **§2** what the crew know
- **§3** the cast they talk about
- **§4** the talk format, which every writer uses
- **§5** how the talk runs

---

## 1. What they are

They are server-spawned zombies, dressed and pacified: the route Bandits and
Week One use (ADIRONDACK.md §10). They wear the mod's own duty uniforms, and
sometimes a species look (`TrekLook_*`), so the crew is mixed:
Trill, Bajoran, Betazoid, Klingon, Andorian, Vulcan and human.

| Division | Uniform | Where they work |
|---|---|---|
| Command | `TrekUniformDutyCommand` | Bridge, the Ready Room, anywhere |
| Operations | `TrekUniformDutyOperations` | Engineering, the transporter room, security, the galley |
| Sciences | `TrekUniformDutyScience` | Sickbay, the science stations |

The talk system (§4, §5) does not care what the crew are made of. It needs
people with a position, a deck, a division and an id that every client can
find.

---

## 2. What the crew know — the brief for anybody writing a line

Binding, and taken from LORE.md 1a–1c and COMMS.md. **Read those first** for
anything that touches the story.

- **The year is 2435.** The TNG, DS9 and Voyager era is history to them,
  fifty-odd years back. People from that era can be mentioned as history, and
  their names are fine (Picard, Janeway, Sisko, Phlox), but nobody aboard
  knew them.
- **The ship:**
  - The U.S.S. Adirondack is a science ship about Voyager's size, with 141
    crew.
  - She has been **parked in orbit above a hidden outpost since before
    February**, surveying a world that is a near-perfect copy of 1990s Earth.
    "Observe only" is policy: parallel development, cf. the Miri anomaly,
    non-interference per the Uxbridge determination.
  - The first survey logged the world as a sensor fault.
- **9 February: she was disabled from the inside.**
  - Warp and impulse are gone, but she is intact, crewed and fed: "a very
    expensive orbital platform".
  - Long-range comms have been dark ever since. **Starfleet does not know they
    are here.** Nobody is coming.
  - **Power works.** The warp core runs the ship; dilithium is precious.
  - **The transporters work.** That is the whole lifeline.
- **Late June: the county below died in two days.** The crew watched it on
  the sensors. Everybody has an opinion about why.
- **Eleven of the crew were on the surface and chose to stay** for the
  fieldwork. Some have been beamed up since (the rescued ensigns). Some have
  not. Not knowing is a wound on this ship.
- **Lt. Lucy Shepard** is the cultural survey specialist. She stayed down
  there longest, came up on 9 July, and is aboard now. The shuttle full of
  1990s furniture is hers, and the crew have opinions about that too.
- **The theories.** Crew may argue them, hedged; none is settled:
  - Section 31, which is what Shepard believed;
  - the Q theory, respectable and held by sensible people;
  - somebody aboard: the sabotage was from inside, and everyone knows it.
- **The truth** is a rogue Changeling grafting Founder virus onto Borg
  nanoprobes. **Crew never state it outright.**
  - Rare `lore` scenes can brush past it: rumours from sickbay about
    "confusing markers", Okafor looking shaken, somebody quoting the Doctor's
    *"I can support the chemistry. I cannot support the author."*
  - The Douwd and Tucker Gold: **nobody aboard knows.** The oddities are fair
    game. Dilithium lies in wild ground and never in town. Their calendar says
    1993 and ours says 2435. A wrong street name is canon.
- **Morale:** cabin fever, rationed replicator time, letters home that cannot
  be sent, dark humour, and holodeck time that is also rationed. It is also
  Starfleet: people are kind to each other, the work goes on, and nobody is a
  villain. The dead below were *people* (LORE.md 1c: "the place is
  manufactured and every person on it is real"). Nobody jokes about them.
- **You, the player.** The crew do not know who you are (COMMS.md:
  "never adjudicated").
  - In uniform, you are one of them and they treat you like a crewmate they
    can't quite place.
  - Out of uniform, you are a curiosity: *"That's a strange outfit."*
  - The transporter room knows somebody has been beaming survivors up and may
    thank you without being sure.

**Never:**
- real actors' likenesses, or impersonating canon characters as speakers;
- a speaker who *is* Shepard, the Doctor or Okafor (they belong to the comms
  channel and the tapes; the crew may **mention** them);
- the Changeling stated as fact;
- anything cruel about the dead;
- lines over **80 characters**. They are drawn over a head, so split long
  speech across two lines.

---

## 3. The cast they talk about

Original characters. The crew mention them, and only generic crew roles speak.

| Who | What |
|---|---|
| **Captain Imogen Vale** | Human, commanding officer. Steady, dry, tired, and has not slept properly since February. |
| **Cmdr. Okafor** | The Section 31 officer (COMMS.md). The crew know him as the quiet one from Starfleet Intelligence liaison. The rumours are worse. |
| **Lt. Cmdr. Tovin Rhel** | Bajoran chief engineer. Has taken the sabotage personally. Talks to the warp core. |
| **Dr. Sela Anwar** | Human chief medical officer. Works alongside the EMH and argues with him constantly and fondly. |
| **Lt. Kess th'Zoran** | Andorian operations officer. Blunt; runs the transporter schedule. |
| **Ensign Pell Daro** | Trill helm officer with nothing to steer. Joined to a symbiont with three previous hosts' worth of opinions. |
| **Lt. Ilsa Tren** | Betazoid counselor. Busy. |
| **Petty Officer Hanna Grieg** | Human, runs the galley. Real cooking on principle; replicator time is rationed. |
| **Lt. Lucy Shepard** | See §2. Mentioned often, never a speaker. |
| **The Doctor** | The EMH. Mentioned often, never a speaker. |
| **The eleven** | The surface team. Writers may name individual missing crew, using `C.EnsignGivenNames` and `C.EnsignSurnames` or new names. |

---

## 4. The talk format

The talk is data, written in plain text files under `design/crew/*.txt` and
compiled by `tools/gen_crew_talk.py` into:
- `TREK_CrewTalk.lua`, the tree the server walks;
- `Print_Text_TREK_CREW_*` keys in `Translate/EN/Print_Text.json`, the words.

The generator checks everything (§4.4) and refuses a broken tree.

### 4.1 Scenes: a conversation between crew members

```
scene: headache
where: sickbay
cast: patient=any, doc=sciences
weight: 3

= start
patient: Doctor, I've had a headache since the end of gamma shift.
       | Got a minute? My head's been pounding since yesterday.
doc: Sit down. When did it start?
-> exam 3, joke 1, brush 1

= exam
doc: Follow the light. ... Good. Other way.
patient: Is it bad?
doc: It's a headache. You've been sleeping four hours a night.
-> sleep 2, coffee 1

= joke
patient: Before you ask: no, I haven't been hitting my head on anything.
doc: That is exactly what people who hit their heads on things say.
-> exam

= sleep
doc: Eight hours. That's an order, and I'll tell Tren if you don't.
patient: The counselor? That's cruel.
-> end

...
```

- **`scene: <id>`** is lowercase, unique across every file, and starts a scene.
- **`where:`** is one or more place tags, comma separated:

  | Tag | Room |
  |---|---|
  | `bridge` | Bridge |
  | `readyroom` | the Ready Room |
  | `lounge` | Lounge |
  | `galley` | Galley |
  | `quarters` | Quarters 1–4 and their baths |
  | `habitat` | Deck 2's corridor and quarters |
  | `transporter` | Transporter Room |
  | `sickbay` | Sickbay, Medical Lab, the CMO's office |
  | `engineering` | Main Engineering |
  | `corridor` | any deck's corridor |
  | `lift` | a turbolift car |
  | `any` | anywhere |

- **`cast:`** is two to four roles, `name=requirement`. The requirement is one
  of:
  - `any`;
  - a division: `command`, `operations`, `sciences`;
  - a job: `medical` (sciences), `engineer` (operations), `security`
    (operations), `helm` (command).

  The first role speaks first.
- **`weight:`** is how often this scene is chosen against others that fit
  (default 1).
- **`tags:`** is optional:
  - `lore` for a scene that touches the story (§2). A lore scene is chosen
    at a quarter of its weight and at most once per world per player.
  - `rare` halves the weight.
- **`= <node>`** starts a node. Every scene has `= start`.
- **`role: text | text | text`** is one line. The alternatives after `|` are
  chosen at random each time it plays. A line may continue onto the next
  line with a leading `|`.
- **`-> a 3, b 1, c`** ends a node: go to one of these, weighted (default 1).
  **`-> end`** finishes the scene. `-> a` with a single target is a plain
  continuation. A node with no `->` ends the scene.
- **`...`** as a whole line is a beat: nobody speaks for a few seconds.
- **`{doc}`** in a line is replaced by how the other speaker is addressed,
  for example "Ensign Tamura" or "Chief". `{role}` works for any role in the
  cast.

**What a scene should be:**
- two to five minutes end to end when it takes the long way;
- at least three real branch points;
- different on every playing, both in its route and in its line variants;
- ended properly. People say goodbye, get called away, or go back to work.

### 4.2 Barks: one-liners

```
bark: hello
where: any
- Morning. | Evening. | Crewman.
- Excuse me. | Pardon me.

bark: outfit
where: any
- That's a strange outfit you have on. | Is that... from down there?
```

Categories:

| Category | When |
|---|---|
| `hello` | walking past you or near you, in uniform |
| `outfit` | the same, but you are **not** in a Starfleet uniform (§5) |
| `thanks` | transporter room and sickbay only: to somebody who might be the one bringing people up |
| `idle` | said to nobody: working, muttering, humming |
| `arrive` | stepping out of a lift |
| `leave` | stepping into one |
| `species:<x>` | you are that species (`klingon`, `vulcan`, `betazoid`, `bajoran`, `trill`, `andorian`, `talaxian`, `exborg`); a sometimes-alternative to `hello` |

`where:` works as it does for scenes. Every `-` line is one bark, with its
own `|` variants.

### 4.3 Writing well here

- **Specific beats general.** "Rhel's been talking to the core again" is
  better than "Engineering is busy."
- **Let people be good at their jobs,** tired, kind, funny.
- **Every scene needs a reason to exist:** a small problem, a want, a
  change.
- **Seed the world,** lightly: the eleven, rations, the dead county seen
  from orbit, the shuttle full of old furniture, the 1993 calendar,
  dilithium in the wild ground.

### 4.4 What the generator refuses

- a missing `start`;
- a `->` to a node that does not exist, or a node nothing reaches;
- a speaker not in the cast;
- a line over 80 characters;
- a duplicate scene id;
- an unknown `where` tag or cast requirement;
- a tree with a loop that cannot reach `end`;
- a bark category it does not know.

---

## 5. How it runs

- **The director** runs on the server, one per deck, and only while a
  player is on that deck.
  - Every so often it looks for idle crew close enough together to fit a
    scene's cast, in a room the scene's `where` allows.
  - It walks them to face each other and plays the scene one line at a time.
    The pace follows the line's length: about 2.5 s plus 60 ms a character.
  - A scene that loses a speaker (despawned, or pushed away) ends there.
- **Barks.** An idle crew member within three squares of a player may
  bark, with a cooldown per NPC and per player.
  - **Out of uniform** means you wear none of `C.UniformIssue`. Then
    `outfit` is chosen instead of `hello` about half the time.
- **What reaches the clients** is only "this crew member says key K, variant
  V, with these names". Each client looks up the text and draws it over that
  person's head.

---

## 6. As built

### Where things live

| File | What |
|---|---|
| `design/crew/*.txt` | the talk: bridge, transporter, sickbay, lounge (and galley), habitat, engineering, corridors, and ship-wide barks |
| `tools/gen_crew_talk.py` | compiles it. `--check --stats [file]` validates and prints each scene's shortest, typical and longest time |
| `shared/TREK/TREK_CrewTalk.lua` | GENERATED: the tree |
| `Translate/EN/Print_Text.json` | the words, as `Print_Text_TREK_CREW_*`. Shared with the comms channel; each generator replaces only its own prefix |
| `shared/TREK/TREK_Crew.lua` | the roster (species, names, ranks, hair), the spots on each deck, finding a crew member by id, and hit immunity |
| `server/TREK/TREK_CrewServer.lua` | population, scripts, scenes and barks (§5) |
| `client/TREK/TREK_CrewClient.lua` | dressing, quieting, walking and seating, and speech |
| `common/media/clothing/clothing.xml` | `TrekCrewBase`, the empty outfit they spawn in |
| `common/media/AnimSets/zombie/…/trekcrew*.xml` | a person's walk, idle and sit, keyed on `TrekWalk`, `TrekCrew` and `TrekSit` |
| `tools/gen_adirondack_lua.py` | gives every room its place tag and every piece its facing, which is where the crew stand and sit |

### The engine facts it rests on

These come from the Bandits framework and the bytecode (research of
2026-09-25):
- **Simulation.** Each zombie is simulated by one client. The server scripts,
  and the owner walks (`not z:isRemoteZombie()`).
- **Walking is ours, not the engine's pathfinder** (first play-test,
  2026-09-25). The pathfinder does not know walls raised at runtime: it left
  everyone in the lift car, or walked them into bulkheads.
  - `K.route` finds a way over the deck plan: same room, or through a
    doorway, and round furniture.
  - The route is cut into straight legs, and each leg is handed to the
    engine as a short walk of its own (`pathToLocationF`). The engine's walk
    is the only one that animates: the second play-test showed a body moved
    by hand glides.
  - A leg the engine fails, or stalls on for 2.5 s, is slid by hand at
    `K.WalkSpeed`, with `TrekMove` set in case that animation node is
    honoured.
  - A walk that has not arrived after `WalkLimit` stops where it is.
- **On duty.** When somebody steps onto an empty deck, `CS.OnDuty` (70%) of
  its crew are already at their posts. The rest arrive by lift.
- **Identity and appearance.**
  - A zombie's packet carries its outfit id and skin index, nothing more.
    Clothes, hair and mod data are applied on each client from our mod data.
  - The id both sides share is `getOnlineID()`. In single player it is a
    counter in the body's mod data.
- **Pacifying.** `setUseless(true)` is network-synced and stops them
  noticing anybody. In multiplayer it is set only while they stand still,
  as Bandits does.
- **Hits.** `setAvoidDamage(true)` in `OnHitZombie` cancels a hit.
  `setGodMod` does not work on zombies.
- **Spawning.** `addZombiesInOutfit` returns nothing when the sandbox has
  zombies set to None. Then the ship is empty, and the log says so once.

### What only the game can show

The sim checks the logic end to end, in single player and with two clients.
These depend on the engine and have not been seen yet:
1. **Walk and idle:** do the crew walk and idle like people? This depends on
   the animation nodes being picked over the zombie ones.
2. **Sitting:** does the sit pose hold, and at the right spot in the chair?
3. **Pathfinding:** does it find its way over runtime-built decks and
   through the auto doors?
4. **Looks:** does the species look render on a zombie body, and does the
   skin come out human?
5. **Speech:** is it drawn above heads in multiplayer, and on the right body?

If the walk or pose is wrong, the fix is in the XML. If the crew never
leave the lift car, it is the pathfinding.

### Tuning

These numbers are at the top of `TREK_CrewServer.lua`:

| Setting | What it controls |
|---|---|
| `SpawnGap` | time between arrivals |
| `StayMin` / `StayMax` | how long they linger at a post |
| `WalkLimit` | how long a walk is given before they give up on it |
| `TasksMin` / `TasksMax` | posts visited before they head back to the lift |
| `ScenesPerDeck` | conversations that can run at once on a deck |
| `SceneGapMin` / `SceneGapMax` | the gap between conversations |
| `BarkReach`, `BarkCrewGap`, `BarkPlayerGap`, `IdleGap` | how close you have to be, and how often they speak |
| `LineBase`, `LinePerChar` | how long each line stays up |

Crew per deck is `K.Population` in `TREK_Crew.lua`.
