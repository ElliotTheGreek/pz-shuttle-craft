# Roadmap 2 — The ship needs you

Future work after `ROADMAP.md`. The first roadmap built the shuttle and its systems. This roadmap turns them into a progression and mission loop.

This is a design document only. Nothing below is implemented yet. The rules in `DEV_GUIDE.md` and `MULTIPLAYER.md` remain binding: the server owns ship power, probes, missions, rewards, and world objects; clients request actions and display authoritative results.

---

## The campaign arc

1. A new shuttle begins landed but almost completely without power.
2. Its emergency reserve can fabricate and launch only a couple of probes.
3. A probe travels in a random straight direction across a great map distance and reports useful contacts along its route.
4. At least one opening probe leads to reachable dilithium.
5. The player travels there on foot or by ordinary vehicle, recovers the crystal, returns, and brings the shuttle online.
6. Once commissioned, the shuttle begins receiving optional distress calls.
7. The first mission is a downed Starfleet ensign wearing the mod’s first classic uniform.
8. The player finds the ensign and transports them to safety for a reward.

The dependency order is deliberate: uniforms before the ensign; contacts before probes; probes before the cold start; and the rescue mission after persistent contacts and deferred world placement work.

---

# 1.4 — The first wardrobe

Add a classic Star Trek-style uniform as the mod’s first custom outfit.

## Initial uniform

Begin with one polished set:

- division-coloured tunic or top;
- dark trousers;
- optional communicator or rank detail if it remains readable at game scale;
- male and female body support;
- inventory icons vetted at actual display size;
- normal clothing dirt, blood, damage, wetness, insulation, and condition behavior;
- no arbitrary stat bonus or armour-like protection.

Once the pipeline is proven, add command, operations/security, and science/medical variants. Trousers can be shared. Rank should remain cosmetic unless a later crew-role system gives it a purpose.

## Build 42 clothing research

Current Build 42 references describe two related layers:

1. **Wearable items** use ordinary item scripts plus per-item clothing XML. Each custom clothing item has a unique GUID registered in `media/fileGuidTable.xml`, with its model, texture, and icon under the mod’s media folders.
2. **Named outfits** are defined in `media/clothing/clothing.xml`, with separate male and female compositions. These are used by the outfit manager to dress zombies, mannequins, and similar spawned appearances.

Sources consulted for this roadmap:

- PZwiki: *Creating a clothing mod*;
- PZwiki: *Mod structure*;
- PZwiki: *clothing.xml*;
- PZwiki: *Outfit*.

Those references include Build 42 information but carry version warnings. Before implementation, inspect the installed 42.20.4 files and a working Build 42 clothing mod. Match the installed game rather than trusting a guide blindly.

## Verify-first plan

1. Find the closest vanilla uniform-like top and trousers.
2. Trace each through item script, clothing XML, GUID table, model, and texture.
3. Determine whether custom textures on vanilla clothing geometry are sufficient.
4. Use a custom rigged mesh only if the uniform genuinely needs a different silhouette.
5. Prove male/female behavior, blood, dirt, holes, tint, masks, washing, and repair.
6. Build one minimal test item first and verify spawn, wear, animation, save/load, and multiplayer visibility.
7. Build the finished uniform and named ensign outfit only after that proof.

Clothing geometry is rigged to the character and is a different problem from the static weapon and fixture meshes already in this project.

## Distribution and replication

Uniform pieces should be available through:

- a small issued set in ship storage;
- seeded default replicator patterns;
- the future downed ensign’s appearance;
- later mission rewards where useful.

Cabin stock additions reach new worlds only because existing containers are never restocked. Existing saves can receive uniforms through newly seeded default patterns without resetting learned patterns.

The replicator makes the individual inventory items, not a named outfit record. Uniform fabrication uses the normal energy rules.

## Acceptance

Verify both body types; ordinary movement, combat, sitting, and vehicle poses; dirt and damage; equip and unequip; save and reconnect; another player seeing the outfit; inventory and ground appearance; cabin stock; and replication.

---

# 1.5 — Long-range probes

Probes turn ship energy into information. They launch from a ship interface, initially a science page on the helm unless play shows that they need a separate console.

## Player experience

A probe:

1. consumes energy to fabricate and launch;
2. receives a randomized bearing;
3. travels in a straight line across a great distance;
4. scans a corridor along that line;
5. reports contacts it found;
6. creates persistent shared map markers;
7. is consumed whether it finds anything or not.

The first contact type is **dilithium**. The system must also support **downed personnel** for a future update. Later contacts might include distress beacons or wreckage, but those are not part of the first probe milestone.

## Logical flight

The first probe should not be a physical object moving through thousands of unloaded squares. Use:

- a launch effect at the shuttle;
- a server-owned logical job containing origin, bearing, range, corridor width, and progress;
- a sliced scan that cannot lock the game;
- delayed reports;
- optional client-side LCARS or map animation;
- no persistent object along the route.

If a visible projectile is added later, it is presentation only, like the photon torpedo’s client-side flight.

## Range and opening guarantee

Configuration should eventually define distance, corridor width, work per tick, report delay, energy cost, and stored-contact cap.

“About a mile” must be tuned by actual Project Zomboid travel time rather than literal conversion.

Random probes may find nothing, but the opening cannot depend on pure luck. One initial emergency probe must be guaranteed to report reachable dilithium. Later probes are honest searches and may return empty reports.

Possible mechanisms:

- choose or seed a valid contact inside an opening corridor;
- make emergency probes scan a wider mineral corridor;
- bias one opening bearing toward a reachable source;
- provide one bounded recovery launch if no usable contact has ever been found.

## Unloaded-world problem

Ordinary loot may not exist as live items until a container is loaded or rolled. A probe must not inspect distant live squares, force chunks to load, or create orphan squares.

Implementation research must choose between:

- recording naturally spawned crystals when loot creates them;
- mission-owned dilithium contacts at known coordinates;
- choosing eligible world metadata and materializing the crystal only when a player legitimately loads the chunk;
- another verified server-safe source of unloaded-world information.

The likely first solution is a mission-owned dilithium cache. The probe discovers a compact contact record. When a player approaches and loads the chunk, the server validates the area and places or confirms the crystal.

## Contact records

A contact should contain:

- unique id;
- type (`dilithium`, later `downedPersonnel`);
- approximate or exact coordinates;
- discovery time and probe id;
- status (`reported`, `investigated`, `recovered`, `completed`, or `expired`);
- optional mission id.

Contacts can grow, so they do not belong in the moving ship table that is transmitted whole on frequent commits. Use a separate bounded mod-data key, following the replicator pattern-store precedent.

## Map markers

Research the ordinary-client Build 42 map-symbol API before committing to an implementation. Confirm creation, transmission, save/load, and removal semantics, and avoid admin/debug-only calls.

Broad probe results should show uncertainty honestly—such as a search circle or corridor—rather than pretending to identify the exact cupboard. The tricorder resolves the final close-range position.

## Interface and energy

The probe page should show:

- energy cost and current reserve;
- emergency launches remaining during cold start;
- active probe and estimated report time;
- recent reports and unresolved contacts;
- **Launch probe** and map focus controls.

It must work with a controller. Launch requires confirmation.

Fabrication and launch are one atomic server transaction: validate access, spend energy once, and create the logical job. The probe does not need to exist as an inventory item.

Support one active probe initially.

## Multiplayer

- The server chooses the bearing and owns progress.
- All crew see the same probe and contacts.
- Racing launch requests create one job and one deduction.
- Reconnecting clients receive active jobs and contacts.
- A probe continues if its launching player disconnects.
- Contacts are shared ship knowledge, not private markers.

An honest empty result is valid after the opening guarantee. An engine error is not an empty result and must log a warning.

---

# 1.6 — Cold start: earn the shuttle

Once probes work, a newly created shuttle begins in an emergency low-power state.

## Initial state

- The shuttle is landed and physically accessible.
- The hatch, emergency lighting, and probe interface work.
- There is not enough normal power for flight or transport.
- The replicator and EMH are unavailable.
- No spare crystal is installed.
- Emergency power supports approximately two probe launches.

The shuttle cannot begin overhead: without transport or flight, the player could not reach the helm that launches the recovery probes.

Initial hull placement must wait for loaded chunks and a valid 3x5 footprint near the player. Never build in an unloaded chunk or silently choose a blocked site.

## Explicit commissioning state

Cold start must be explicit persisted progression, not merely a low reserve value. Conceptually track:

- cold start active;
- emergency reserve remaining;
- opening contact found or not;
- crystal installed or not;
- ship commissioned or not.

Automatic crystal loading or service passes must not accidentally bypass the opening.

## Opening loop

1. Reach the powerless shuttle.
2. Read the emergency helm status.
3. Launch a probe.
4. Receive its dilithium report.
5. Travel to the contact by foot or ordinary vehicle.
6. Use the tricorder to resolve the final trace if needed.
7. Recover the crystal.
8. Return and load it into the warp core.
9. Commission the shuttle.

Power-up should be clear: warp-core light and sound, a ship-wide cue, helm status changing to operational, and flight, transport, replication, and EMH access becoming available.

## Compatibility

Cold start applies only to new ships. It must never drain an existing save.

A sandbox option should likely offer:

- **Cold start** — earn the first crystal;
- **Commissioned** — retain the current ready-to-use opening.

Existing worlds migrate as commissioned unless they explicitly began cold start. Never infer a new campaign merely from low reserve.

## Soft-lock prevention

The campaign must survive missed random routes, invalid terrain, target loss, player death, ownership changes, server restart, and unusual modded maps.

During cold start, emergency reserve is restricted to probe launches and cannot be consumed by other systems. The opening crystal remains mission-owned until recovered. If an engine failure loses it, provide a bounded recovery route rather than leaving the world unwinnable.

---

# 1.7 — First mission: the downed ensign

After commissioning, the shuttle receives an optional distress request from a Starfleet ensign roughly a mile’s journey away.

The player may accept, travel to the contact, find a static downed figure in uniform, and transport them to safety. The figure disappears and the ship receives a reward.

## Static model, not full NPC

The first ensign has no pathfinding, combat, needs, follower logic, or remote simulation. They are a server-owned static world object or model using the uniform design.

Right-click actions:

- **Examine the downed ensign**;
- **Transport the ensign to safety**.

The model must read as an injured person, not a corpse or loot prop. If imported, apply the EMH lessons: fit by height, verify facing, render before game testing, and do not assume auto-unwrapped texture directions align with the world.

## Mission offer

The request includes:

- an LCARS message and restrained audio cue;
- approximate distance and signal quality;
- **Accept** and **Decline**;
- no punishment for declining;
- no repeated prompt every minute;
- a queued record readable later from the ship interface.

## Target selection and placement

Choose a destination that is inside the playable world, on reachable solid ground, outside water and protected safehouses, far enough to require a journey, and close enough to remain enjoyable.

The server persists the target but does not place the model until a player legitimately loads its chunk. It then validates the square, searches locally if necessary, and transmits the completed object.

An unloaded square means “cannot tell,” not “the ensign is gone.” Pending placement and removal must survive save/load and be retried when the chunk returns.

## Discovery

The distress call supplies a coarse region. A probe may later discover or refine `downedPersonnel` contacts, but the first mission must not require another random probe immediately after cold start.

Near the destination, the tricorder finds the personnel contact. Long-range systems locate the region; the tricorder locates the person.

## Rescue

Use a tested right-click margin because a prone or tall model may not resolve to its own floor square.

The server validates mission id, object id, access, player distance, object presence, and incomplete status. It then atomically:

1. completes the mission;
2. removes and transmits removal of the ensign;
3. clears the marker;
4. grants the reward exactly once;
5. informs the crew that the ensign reached safety.

The first version does not need to place the rescued ensign aboard. A safe off-screen recovery avoids creating a second persistent person object.

## Reward

Preferred first reward:

- a new uniform division variant or replicator pattern;
- plus a modest practical supply.

Avoid immediately awarding another full crystal after the opening crystal. The reward is committed with mission completion, so reconnects and simultaneous interactions cannot duplicate it.

## Multiplayer

Mission offer, acceptance, target, and completion are shared ship data. Any authorized crew member can rescue the ensign. All clients see one model, one marker, and one completion. Racing rescue requests produce one removal and one reward. Late joiners receive active missions, and missions continue if the accepting player disconnects.

---

# Shared architecture

## Separate bounded stores

Contacts and mission history can grow and must not live in frequently transmitted ship state. Use separate bounded stores and explicit request/receive handshakes for joining clients.

Keep unresolved contacts, retain only a bounded number of resolved records, and reduce old missions to compact log entries or discard them.

## Common lifecycle

Probes, distress calls, tricorders, and map markers share contact types and states:

```text
unknown -> reported -> investigated -> recovered/completed
                                  -> expired/invalid
```

Initial types are `dilithium` and `downedPersonnel`.

## Authority and chunk discipline

Every command needs a server handler, access checks, object/distance validation where relevant, idempotency, player-facing denial text, and simulated two-client coverage.

Never inspect live squares in unloaded chunks, create orphan squares, or place the ensign or crystal cache before a player loads the chunk. Persist intent and retry later. Use supported transmit calls for every server world mutation.

---

# Suggested implementation order

1. **Prove one custom clothing item.** Inspect installed files, build a minimal uniform top, and verify both bodies, animations, save/load, and multiplayer.
2. **Finish the uniform.** Add icons, storage, replicator patterns, division variants, and the named ensign outfit.
3. **Build contact persistence.** Add bounded stores, two-client publication, map markers, and tricorder display using synthetic contacts.
4. **Build one logical probe.** Add sliced flight, atomic energy spending, restart persistence, and synthetic reports.
5. **Connect probes to dilithium.** Solve unloaded-world contacts and guarantee a reachable opening source.
6. **Build cold start.** Add commissioning state, system gates, emergency power, first-crystal recovery, and power-up.
7. **Build the ensign mission.** Add offer UI, deferred target placement, tricorder contact, right-click rescue, atomic reward, and cleanup.

---

# Acceptance stories

## Uniform

A player takes a uniform from storage, wears it, saves, and reconnects. Another client sees it during normal movement and vehicle poses. The player can replicate a replacement from the seeded pattern.

## Probe

A crew member launches from the helm with a controller and sees one energy deduction. The server continues after that client disconnects. Every crew member later receives the same contact and marker.

## Cold start

A player reaches a landed but powerless shuttle, launches an emergency probe, follows its report, recovers dilithium, and loads the core. The ship powers up. Restarting at any point neither resets progress nor strands the save.

## Ensign rescue

The crew accepts a distress call, travels to the marked region, uses the tricorder to find a downed uniformed ensign, and transports them to safety. All clients see the model disappear, the marker clear, and the mission complete. The ship receives exactly one reward.

---

# Decisions left for prototypes

- helm page versus separate science console;
- exact probe distance, corridor width, duration, and energy cost;
- enjoyable tile distance for “about a mile”;
- ordinary-client map marker API;
- representation of unloaded-world dilithium contacts;
- custom uniform mesh versus custom texture on vanilla geometry;
- separate division items versus texture choices;
- default cold-start sandbox setting;
- exact ensign reward;
- static posed mesh versus another safe non-AI representation.

The goals are settled even where mechanisms remain open: probes turn emergency power into a route to dilithium; dilithium earns the functioning shuttle; uniforms establish a Starfleet identity; and the downed ensign turns those systems into the mod’s first rescue mission.
