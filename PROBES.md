# Long-range probes

The working guide for `ROADMAP2.md` 1.5, in the shape `REPLICATOR.md`,
`EMH.md` and `UNIFORMS.md` use. `MAP_MARKERS.md` is the research that decided
how contacts reach the map; this is what was built on top of it.

---

## 1. What the player does

Right-click anywhere aboard → **Shuttlecraft** → **Long-range sensors**
opens the console, the mod's fourth LCARS panel:

```
Reserve: 4750 / 5000 units                          Probes: 3 / 8
Probe in flight: 63%
[============================------------------]
  FABRICATE (250)            LAUNCH PROBE
Contacts on file: 3
  Dilithium trace: 1830 tiles NE
  Life sign: 640 tiles SW
  SHOW ON MAP
```

**Energy buys a probe; a probe buys a launch.** Those were one action and are
now two, because a ship that turns energy into a *countable* thing reads
better than one that turns energy into an event: "three probes aboard" is a
state you can plan around, where "830 units of reserve" is arithmetic you have
to do first.

**There is no new fitting.** The console was going to be one and would have
cost one of twenty-four deck squares and a BuildingEd change; it is reached
the same way the helm is. It was briefly a right-click submenu, which worked
and read as a list of settings rather than a station on a starship -- and gave
a probe in flight nowhere to show progress.

## 2. What happens

1. The client sends `launchProbe`. It knows nothing and decides nothing.
2. The server checks crew access, that the player is **aboard** (against its
   own copy of where they are), and that no probe is already up.
3. It spends `C.ProbeCost` from the reserve, burning a crystal if it has to,
   and creates the logical job — **all in one handler**, so racing launches
   make one probe and one deduction.
4. The server picks the bearing. Not the client: a client that could name the
   direction could name the one with the crystal in it.
5. Every game minute the job advances by `C.ProbeWorkPerTick`. Progress is
   persisted, so a restart mid-flight resumes rather than losing the probe and
   the power that bought it. It runs outside the cabin-loaded branch, so it
   keeps flying whether or not anybody is aboard.
6. On arrival it rolls against `C.ProbeFindChance`. A hit adds a `dilithium`
   contact scattered up to `C.ProbeReportSpread` tiles off the endpoint and
   marked **approximate**; a miss logs that the probe returned nothing.

## 3. The numbers, and why

| | | |
|---|---|---|
| `C.ProbeCost` | 250 | to **fabricate** one; a crystal is 5000, so twenty probes |
| `C.MaxProbes` | 8 | so energy cannot be banked until the decision goes away |
| `C.ContactRevealRadius` | 120 | squares of map uncovered around a contact |
| `C.ContactPlaceRadius` | 6 | how far the ship will look for ground to put it on |
| `C.ProbeFlightTicks` | 60 | advanced once a **game minute**, so one game hour |
| `C.ProbeWorkPerTick` | 1 | |
| `C.ProbeMinDistance` / `Max` | 1200 / 2400 | tiles |
| `C.ProbeFindChance` | 0.65 | an empty report is a real outcome |
| `C.ProbeReportSpread` | 60 | tiles of uncertainty in a long-range fix |

The flight is advanced per **game minute and not per server tick**. At sixty
ticks a second a three-hundred-tick flight is five seconds, which is not a
journey across a great map distance, it is a loading pause.

The spread is what keeps the tricorder worth having. A probe that named the
exact square from two thousand tiles away would make the whole close-range
half of the design pointless — ROADMAP2: *"Long-range systems locate the
region; the tricorder locates the person."*

## 4. Where things live

```
shared/TREK/TREK_Probes.lua        the store: contacts, the active job, the bounds
shared/TREK/TREK_Config.lua        every number above, plus the kinds/statuses
server/TREK/TREK_Server.lua        launchProbe, and S.serviceProbe on the minute tick
client/TREK/TREK_ProbeUI.lua       the sensor console (the LCARS panel)
client/TREK/TREK_Menu.lua          the one option that opens it
client/TREK/TREK_MapContacts.lua   contacts drawn on the world map
shared/Definitions/TrekMapSymbols.lua   the symbol registration (generated)
tools/gen_map_symbols.py           the two glyphs and that registration
```

## 5. Engine facts, so they are not re-derived

- **Lua cannot make a shared, persistent map symbol.** The half of the
  engine's annotation system that does that is not exposed. Contacts are the
  mod's own bounded store and symbols are a view rebuilt on map open. Full
  reasoning in `MAP_MARKERS.md`.
- **`addTexture` takes world squares**, the same coordinates the mod already
  speaks, and a symbol id nothing registered draws nothing at all.
- **`ZombRand` is an ordinary global** — 424 vanilla call sites, only seven of
  them under `DebugUIs/`.
- **`math.atan2` is Kahlua-only** and was removed in Lua 5.3. The bearing here
  uses two ratio comparisons instead, which is true in both.

## 6. What will bite you

**A contact's kind and status are closed sets and both are checked.** A status
nothing recognises makes a contact that reads as neither live nor resolved:
never drawn, never pruned, there for the life of the save. Both are refused
with a WARN rather than stored.

**The history bound is on a property `setStatus` changes.** Pruning only when
a contact is *created* leaves the resolved list one over its cap permanently,
because a record becomes history after the add that last swept. `P.prune()` is
called from both.

**The "impossible" refusal is loud on purpose.** If `Probes.active()` says no
probe is up and `begin()` refuses anyway, the handler refunds and logs a WARN.
Without that line the branch is invisible — it refuses with the same reason
the guard above would have given, and neither a test nor a log could tell the
two apart. That was a real mutation escape.

**Nothing tests inside a submenu unless the harness models one.** `pz_sim`'s
`addSubMenu` was a no-op, so every option one level down was invisible. The
sensors submenu is gone, but the lesson outlived it and the harness keeps the
fix.

**Never give the mod its own map symbol category.** Two symbols in a
"Starfleet" category made *opening the world map* throw, inside vanilla:
`ISWorldMapSymbols` lays a category out eight buttons to a row and then reads
`joypadButtonsY[floor(rows / 2)]`, so one row indexes `[0]`, which is nil, and
`#nil` throws. Nine symbols is the minimum. The mod's join `Locations`.

**A per-cent sign beside a `%1` comes out mangled.** "Probe in flight -- 16$s%"
was what a player saw. Put the sign in the *argument*; no other translation in
this mod has a literal one, which was the tell.

## 7. Not built, and still to settle in game

**Seen working:** nothing yet. This is the first version.

1. **The loop end to end** in a fresh world: fabricate, launch, wait an hour
   of game time, read the report, open the map, walk there, pick the crystal
   up and watch the contact retire.
2. **Whether an hour is the right wait**, and whether 250 is the right price.
   Both are guesses and both are one constant.
3. **Whether the contact symbol reads** on the real map among street names and
   the player's own annotations, at the zoom people actually use.
4. **Whether the revealed area is the right size.** 120 squares either side is
   enough to see the roads in; it may be too generous or not enough.
5. **Two clients** -- the store is shared and tested as such in the
   simulation, but the map view has never been drawn on two machines, and the
   reveal is per-player by design.
6. **A probe across a server restart.** Progress is persisted and tested; the
   real save/load round trip is not.

## 8. Deliberately not built yet

- **The opening guarantee.** 1.6 needs one probe that certainly finds
  something; `C.ProbeFindChance` is deliberately not that mechanism.
- **`downedPersonnel` contacts.** The kind, the symbol and the label all exist
  so that 1.7 does not have to add them in a hurry. Nothing creates one.
- **A corridor scan.** The probe reports one point at its endpoint, not
  everything along its route.
