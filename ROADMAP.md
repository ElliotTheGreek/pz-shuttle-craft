# Roadmap

What the Shuttlecraft mod has, what is proven, and what comes next, in order.
One file since 2026-09-26: it replaces the old `ROADMAP.md` (the shuttle and
her systems, 1.0-1.3) and `ROADMAP2.md` (the progression loop, 1.4-1.8), both
of which had drifted a long way behind the code.

`README.md` says what the mod does. `DEV_GUIDE.md` says how to work on it
without breaking it (**read *Rules that exist because they were broken*
first**). `MULTIPLAYER.md` is the rule every feature obeys: the server owns the
ship and the world, a client only asks, and nothing may depend on admin
rights, `-debug`, or one particular PC. Each system has a working guide, named
in the table below. **This file is the index and the queue; the guides are
the detail.**

---

## 1. Where it stands

**Version 1.9.0, build revision 29.** Workshop package staged, not published.

*Played* means somebody has used it in a real game. *Built* means static checks
and the simulated server with two clients pass, and nobody has played it yet.

| System | Guide | State |
|---|---|---|
| Transporter, landing, hatch, the void outside | `DESIGN.md`, `MULTIPLAYER.md` | **Played** |
| Flight (one hover height, sandbox *Hover height*) | `PILOTING.md` | **Played** at level 5, and with two people at level 1 (2026-09-23). The obstacle guard has not met a tall building yet |
| Photon torpedoes | `PHOTON_TORPEDOS.md` | **Played** with a mouse. Controller aim is built and has not been held |
| Phaser: model, bolts, cutting trees and doors | `PHASERS.md` | **Played** |
| Blades: bat'leth, mek'leth, lirpa, ushaan-tor | `DEV_GUIDE.md` | **Played**, at the right size |
| Galley food and drinks | `ITEMS.md` | **Played** |
| Interior refit (4x6 cabin, three lockers) | `INTERIOR_REFIT.md` | Built. Only the television is **played** (it plays tapes). The migration from a 6x9 save has not been seen |
| Replicator | `REPLICATOR.md` | **Played** (loads, 4913 items, places). The fixed right-click menu and the tree panel have not been seen since |
| Dilithium and the warp core | `REPLICATOR.md`, `ENERGY.md` | Built. Crystals in wild ground (`TREK_Wild.lua`) came out of a cold-start play |
| Energy: ledger, gauge, dark ship, shields, emergency landing | `ENERGY.md` | Built (phases 0-7) and not played |
| Cold start | `ENERGY.md` 10 | Built. **Played** in part (it is why dilithium lies in wild ground) |
| Medical set | `MEDICAL_SET.md` | Built, not played |
| EMH and the cure | `EMH.md` | **Played** in part: the first cure found two bugs, both fixed (*Aboard means the ship*) |
| Uniforms | `UNIFORMS.md` | **Played** (they wear and draw). Female body not seen |
| Probes and the sensor console | `PROBES.md`, `MAP_MARKERS.md` | **Played** (one empty report taught the feedback) |
| Distress calls and the downed ensign | `ENSIGN.md` | **Played** end to end in single player |
| PADD: books, tapes, the screen | `PADD.md` | **Played** (load, read, recover off a body; the screen's first ring) |
| The Adirondack channel | `COMMS.md` | Built. Only first contact is **played** |
| Tape shelf | `LORE.md` | **Played** (tapes play). Line effects not seen |
| Species, traits, professions, rank | `TRAITS.md` | Built, not played |
| The Adirondack: decks, lifts, doors, machines | `ADIRONDACK.md` | **Played**: beaming across, the decks, the lifts. Her doors on a server, her EMH stations and the lighting still want a look |
| Her crew | `CREW.md` | **Played** twice; walking and sitting still need a look |
| Hydroponics and the galley stove | `FARMING.md` | **Played** 2026-09-26: planted bay, harvest, sowing, cooking |
| Jefferies tubes, hideouts, Turbolift Phobia | `JEFFERIES.md` | Built, not played. **Needs a new world** |
| Contraband | `CONTRABAND.md` | Built, not played. **Needs a new world** |
| Dedicated server | `MULTIPLAYER.md` | Loads cleanly; **nobody has played on it** |

---

## 2. Next, in order

### 2.1 Play the backlog in one fresh world

Everything *built and not played* above, in one sitting in a new world (loot,
crystals, cold start, tubes and contraband all need one). Work down this list;
each guide's own *Not yet seen* section has the detail.

1. **Cold start** (`ENERGY.md` 10.5): spawn near a dark shuttle, launch a
   probe, walk to the crystal, load it, hear the power come up.
2. **The dark ship** (`ENERGY.md` 12): spend to zero, see red light, the
   replicator offline, the Doctor refused; hover to dark over a town.
3. **The cabin** (`INTERIOR_REFIT.md` 7): three lockers, five empty
   containers, the biobed, no climbing over walls.
4. **Medical set** (`MEDICAL_SET.md`): a dose leaves a bite alone, the
   regenerator closes skin, the sweep in front of a horde.
5. **The Doctor** (`EMH.md` checklist): treat, cure, and the moodle clears.
6. **The channel** (`COMMS.md`): a whole call, then a week of the spine.
7. **Traits** (`TRAITS.md` 5): the creation screen, a Trill's first minute,
   the looks, a Vulcan eating steak.
8. **The Adirondack's tubes and hideouts** (`JEFFERIES.md` 7), then
   **contraband** (`CONTRABAND.md` 7).
9. **The crew** (`CREW.md` 6): walking, sitting and speech.

### 2.2 The two-player session

The longest-standing gap in the project. Only flight has been played by two
people. Dedicated server world `trektest2` is set up for it:

```sh
PZ="$USERPROFILE/Zomboid/PZ-Worlds.ps1"
powershell -File "$PZ" start trektest2     # join at 127.0.0.1:16261
powershell -File "$PZ" stop
```

It runs with `Mods=TrekShuttleDev`, `Map=TrekShuttle;Muldraugh, KY`, the mains
off (`WaterShut = 1`) and `AntiCheatSpeed = 2`, so transporter charges are
live. The second machine is the Steam Deck (192.168.39.182). It needs
`Zomboid/mods/TrekShuttle/` **copied by hand** after every change, because a
server cannot push a local mod.

Check, with two people:
- the shared cabin, and loot taken by one gone for the other;
- *Owner and crew* access, and four fast beams saying *recharging* rather
  than kicking;
- the shuttle climbing and hovering, seen from the street;
- a torpedo seen and its fire on both machines;
- another player's phaser bolts;
- the EMH's consent prompt on the patient's screen;
- a pattern scanned by one reaching the other;
- one channel with two PADDs;
- one ensign rescued for one reward;
- the Adirondack's crew seen from both;
- *Offer the Game to...*

### 2.3 Keep the documents true

Brought up to date on 2026-09-26: every guide's status now matches section 1.
The rule that keeps it that way: **when something is seen in game, update
section 1 and the guide's own *not yet seen* list in the same commit.** A
"not yet proven" line decays silently every time the game is played and the
file is not edited -- the television was reported "never switched on" for days
after it had been used (`LORE.md` 8).

### 2.4 Publish

`tools/package_workshop.py` keeps the published item id. The Workshop
description has to say that a dedicated server needs
`Map=TrekShuttle;Muldraugh, KY` and how `AntiCheatSpeed` limits beaming.
**Nothing ships unplayed**, and anything shared needs checking with two
players first (2.2).

---

## 3. Still to build

Ideas, not a plan. One line each, and each points at where its reasoning is.

**Needs a hand in the game, not code**
- Blades' `attachment` offsets: hand and ground, six numbers each, judged in
  a fist (`DEV_GUIDE.md`). The PADD's hand position is the same question
  (`PADD.md` 7).
- Torpedo controller: whether 950 px/s feels right and whether R3 is free on
  a Deck (`PHOTON_TORPEDOS.md`).

**The shuttle**
- Phaser holster (`AttachmentType = HolsterSmall`, with a 32x32 icon), stun
  and kill settings, and a charge for cutting (`PHASERS.md` 8).
- A custom biobed canopy (`INTERIOR_REFIT.md` 8).
- Delete the helm console's assets once the refit migration has been seen in
  a real save.

**The wardrobe**
- The skant, which needs the body-texture pipeline (`UNIFORMS.md` 7).
- Rank pips on the collar (`TRAITS.md` 4.7).
- Named outfits, needed first by a corpse for a lost ensign.

**Missions and the story**
- A lost ensign leaves a body in uniform (`ENSIGN.md` 10).
- Probes that find survivors, not only distress calls.
- A probe that scans a corridor rather than one point.
- How an uncertain contact should read on the map (`MAP_MARKERS.md` 6).
- The death screen: vanilla's lines until the ship is found, then the three
  lines (`LORE.md` 1d, parked).

**Tapes** (`LORE.md` 5). Written so far: the talent night, Tuvix, the six
logs, the six fragments, the ensign's log, Uxbridge, Morn, Kim's exam, the
prisoner, and the holosuite reel. Still unwritten:
- **Tier 1:** Meditation, Field Repair, Leola Root, Ushaan, Mok'bara,
  Dilithium, Tribbles, Wolf 359, Barclay;
- **Tier 2:** tapes found in town, with a loot distribution;
- **Stretch:** the Doctor's opera.

**Traits** (`TRAITS.md` 4.7)
- Temperature for Vulcans and Andorians.
- The android's bandage rule.
- Talaxian whiskers.
- Species preferences for drinks.

**The Adirondack** (`ADIRONDACK.md` 10, `ITEMS.md` 6)
- Posters and art: the plant, the transporter pad, the plaque's IP check, a
  two-storey warp core.
- `bar_corner` is modelled and not placed.
- Rooms: holodeck, science labs, shuttlebay, armoury and brig, captain's
  quarters, gym.

**Items** (`ITEMS.md` 6)
- Combadge, isolinear chips, engineering tools, more medical kit.
- Holodeck chips, replicator ration chits.
- A Bolian dish, spare uniforms by rank, tapes from crew.

---

## 4. Open decisions for the author

- **The helm emblem** was judged a near-exact copy of the Picard-era Starfleet
  insignia. Keep it, or draw something more distinct.
- **The phaser holster**: vanilla's holster slot, or a uniform that provides a
  hip slot (`PHASERS.md` 8).
- **Tier 2 tapes**: findable before the ship is found, or only after
  (`LORE.md` 9).
- **Contraband**: the defaults taken on 2026-09-26 (withdrawal never hurts;
  the Game cured by the PADD *or* the Doctor; *Offer the Game* on in
  multiplayer) are the author's to overturn.

---

## 5. The campaign, as built

What the old `ROADMAP2.md` set out to do, and how it came out:

1. A new world starts **cold** (sandbox default): the shuttle is landed near
   the first player, dark, with two probes and no spare crystals.
2. A probe reports dilithium; **the first probe of a save always finds
   something**.
3. The player walks there, finds the crystal with the tricorder, walks back
   and loads it. The ship is **commissioned**, and everything powers up.
4. After commissioning:
   - **distress calls** begin, and a rescued ensign pays in replicator
     patterns and a rank;
   - **Lt. Shepard calls** the PADD a week later. The channel tells the
     story, and six Tucker Gold fragments found by probe become tapes;
   - the **Adirondack** can be visited: her decks, her crew, hydroponics, and
     the tubes with their hideouts.

**The old section numbers**, still cited in code comments and guides:

| Old reference | Now |
|---|---|
| ROADMAP2 1.4, the wardrobe | `UNIFORMS.md` |
| ROADMAP2 1.5, probes | `PROBES.md`, `MAP_MARKERS.md` |
| ROADMAP2 1.6, cold start | `ENERGY.md` 10 |
| ROADMAP2 1.7, the downed ensign | `ENSIGN.md` |
| ROADMAP2 1.8, the PADD | `PADD.md` |
| ROADMAP step 7 | 2.4 above |

---

## How art gets made

**All icons and images are generated and vetted with the FlowDot Gemini Image
toolkit** (`gemini-image`):

| Step | Tool | Purpose |
|---|---|---|
| Create | `generate-image` | Text → image from a written brief |
| Refine | `edit-image` | One image + instruction → revised image |
| Combine | `compose-images` | Two images → one |
| **Vet** | `analyze-image` | Image + instruction → written critique |

Meshes come from fal TRELLIS (seed 1701) off a Gemini concept, or from the
mod's own generators. Every asset is vetted **at the size it is shown** (icons
at 32x32, against the whole set): does it read, is the silhouette distinct, is
it Star Trek without copying a frame of the show, is the background genuinely
transparent. Icons are generated on flat magenta and keyed by
`tools/key_icon.py`; raws are kept in `design/art/`. Every file is then checked
by `tests/test_assets.py`.

**FlowDot's image storage fills up** (about fifty images). Old ones are deleted
to make room, with the author's go-ahead, and it is full again as of
2026-09-26.

---

## Ground rules

- **Multiplayer first.** Decide what runs on the server and what on the client
  before writing it (`MULTIPLAYER.md`), and extend `tests/test_multiplayer.py`.
- **Verify every new engine call** with three things:
  - `tools/pzapi.py`: does the method exist, and is it public?
  - `tools/javadis.py`: under what condition does it do what it says?
  - a vanilla Lua call site: may Lua call it at all?

  Only Kahlua's standard library exists (no `next`, no `math.huge`).
- **Mutation-check every new test**, one mutation at a time, asserting that
  the edit applied.
- **Add the log line that proves it worked.**
- **Bump `C.BuildRev`** for anything that places or changes an object in the
  cabin. New loot reaches new worlds only.
- **Deploy before saying it is ready to test**: `python tools/deploy_windows.py`.
- **Nothing ships to the Workshop until it has been seen in game**, and,
  for anything shared, seen with two players.
