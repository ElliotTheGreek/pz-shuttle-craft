# Marooned: the third way a world begins

The working guide for the sandbox's third **How the shuttle starts**. It is the
cold start (`ENERGY.md` 10) with the ship lost: she is down and dark somewhere
else in the county, nobody has a combadge, and the only word of where she is
comes off a road map somebody marked.

Built 2026-10-07. **Not played.** Section 8 is what to look at first.

---

## 1. What the player gets

1. They wake wherever the game put them. Nothing says a shuttle exists: no
   note, no Shuttlecraft menu on a right-click, no gauge, no dot on the map.
   Their species, their profession and its kit are all as they chose them.
2. Wherever the county keeps maps (a gas station's rack, a crate of them, a
   glove box that rolled one) there may be an **Annotated Map** beside
   vanilla's. Right-click it, **Read the annotated map**: *"Somebody has
   circled a field east of Muldraugh and written: IT CAME DOWN HERE. 3087
   tiles N."* The spot goes on the world map as a red ringed cross, the ground
   round it is uncovered, and the map opens on it when there is light to read
   by.
3. They cross the county. The shuttle is on open ground at the mark, dark.
   Right-click her hull: **Board the shuttle**, and nothing else.
4. The moment they are aboard (her cabin, or one of her seats): *"You have
   found the shuttle. Combadge online: she will answer you from anywhere
   now."* From then on the menu, the transporter and her dot on the map are
   theirs, and the rest is the cold start's own loop: a probe, a crystal, the
   commissioning.

On a server each player earns their own. The second aboard is told only that
their combadge is online.

---

## 2. The option

`TrekShuttle.StartState`, value 3 (`C.StartMarooned`), and **the default
for a new world** since the day it was built (the author's call): the sandbox
file's default is 3 and an absent value reads as marooned. Cold is 1 and
Commissioned 2, as they were. Like the cold start it is
read **once, by a brand new ship**: a save whose ship has ever been built or
landed carries on commissioned whatever the setting says (`CS.init`).

---

## 3. The state

Everything the cold start writes (`s.commissioned = false`, `s.coldStart`,
no power, no spares, two probes, `s.dark`), and:

| Field | What |
|---|---|
| `s.marooned` | true for the life of the save |
| `s.maroonSite` | the id of the site this world drew, once the first player is on their feet |
| `s.maroonPlaced` | she has been set down on it at least once |
| `s.badged` | a set of **usernames** who have been aboard |
| `s.maroonFound` | somebody has |
| `s.maroonMaps` | how many annotated maps have gone into containers, for the log |

`s.badged` rides the ship's table, which is published whole on every change.
It is bounded by the players a world has ever had and each name is written
once, so that is safe (DEV_GUIDE, *State that is transmitted whole cannot hold
a list that grows*). A username and not a character: somebody who dies does
not lose the ship a second time.

`TREK.Marooned.linked(player)` is the one question both ends ask. It is true
in any world that is not marooned.

---

## 4. Where she is

**Six sites** (`C.Maroon.sites`), open ground beside Muldraugh, West Point,
Riverside, Rosewood, March Ridge and Valley Station. They were read off the
vanilla map, not remembered: `python tools/maroon_sites.py` prints how many
places each has to set her down, `--find` looks for more, and
`tests/test_assets.py` runs the check against the installed map.

- **The draw** (`MS.chooseSite`) happens when the first player is on their
  feet. Sites outside this world are dropped (`U.inWorld`); of the rest, only
  those at least `C.Maroon.minDistance` (1000 squares) from that player are
  drawn from. Muldraugh's site is 170 squares from the middle of Muldraugh and
  the nearest other is about 1,800, so that rules out the town they woke in
  and nothing else. If every site is too near, the farthest is taken.
- **A map with none of the six** (another map mod entirely) is a cold start
  after all: `s.marooned` is cleared, a WARN says so, and she is set down
  beside the first player. A ship nobody can find is a save nobody can play.
- **She is a record until somebody loads her ground.** The server builds only
  where a player stands, so `MS.servicePlacement` does nothing until the
  site's chunk is loaded, then runs the cold start's sliced ring search out to
  `C.Maroon.placeMax` (24 squares) and lands her with `S.land`. Nobody is
  told.
- **Lost before she is commissioned, she is put back on the site**, for the
  cold start's reason: a dark ship overhead can never be reached. Once
  commissioned she is the crew's, and a recall is not undone.

---

## 5. The combadge

There is no combadge item. "No combadge" is `MR.linked(player) == false`, and
it takes away exactly what a combadge would give:

| Where | What changes |
|---|---|
| `TREK_Menu.groundMenu` | no Shuttlecraft menu on open ground; on her hull, *Board the shuttle* only |
| `TREK_Server` `move` | `beamUp` is refused, `noBadge` |
| `TREK_Server` `land`, `recall` | refused, `noBadge` |
| `TREK_MapView.shipSpot` | her orange dot is not drawn |

The hatch is a door and is never asked, which is how anybody gets a combadge
at all. The menu hiding is a courtesy; the server's refusals are the rule
(`marooned_mp` sends the beam straight past the menu).

`MS.serviceBadges` runs every `C.Maroon.badgeTicks` server ticks and links
anybody who is in her cabin (`U.isAboard`) or in one of her seats
(`V.isShuttle(p:getVehicle())`). Polling rather than hooking each way aboard:
there are four ways in already and a fifth would have been a way in with no
combadge.

**The first aboard also finds her**: `s.maroonFound`, the map's mark retired,
and no more annotated maps.

---

## 6. The maps

`TrekShuttle.TrekAnnotatedMap`: a Normal item with vanilla's map icon and
world model. The mark is not in the item. Every map says the same thing, and
what it says is the ship's own contact.

### 6.1 Where they come from

`Events.OnFillContainer`, on the authority. When the engine rolls a container
and it comes up holding one of vanilla's maps (`InventoryItem.IsMap()`), there
is a `C.Maroon.mapChance` in a hundred (50) that an annotated one goes in
beside it, while she is marooned and not yet found.

**At the roll, not in the loot tables**, which is how dilithium is seeded.
A table is merged before the sandbox or the ship can be asked, so a table
entry would put annotated maps in every world, and in every other world they
point at nothing. The roll also follows any map mod's own map places for free.

The engine facts, from the bytecode:

- `ItemPickerJava.fillContainerInternal` opens with `if (GameClient.client)
  return` (bci 0-18): a client never rolls loot and the event is never raised
  there. `SIM.fillContainer` models that.
- The event is raised as the method's last act, with `(roomName,
  containerType, container)`, after the table's items are in. On a server the
  container's contents are sent on request afterwards
  (`RequestItemsForContainerPacket`), so an item added in the handler goes
  with them.
- `IsMap()` is true for the engine's own `MapItem` class only. The mod's map
  is a Normal item and answers false, which is what stops one annotated map
  seeding another on a re-roll.
- Vanilla's own call site for the event is `server/Items/LootLog.lua`.

### 6.2 Reading one

`readShuttleMap`, with the item's id. The server finds the item in the
asker's own inventory and checks it is an annotated map, then:

- no site (a world that is not marooned) or already found: `stale`, and the
  client says the marks are old news;
- otherwise one `shuttle` contact (`C.ContactKinds`), on the site's point and
  `approximate` until she is down, then moved to where she really stands. A
  second reading makes no second mark.

A contact, so everything the probes built serves it: every client draws it
(`TrekContactShuttle`, a red ringed cross from `tools/gen_map_symbols.py`),
uncovers the ground round it, and loses it when it is retired.

The reader's client says where and how far, and opens the map on the mark
through vanilla's own read-the-map action (`MV.showAt`) when the map is
allowed and there is light. In the dark the note is all they get.

---

## 7. What would have bitten you

- **A guard that could not be reached, twice.** `MS.link` tested for an
  existing combadge after its only caller already had, and the map's handler
  tested `s.marooned` beside a `site` that is nil in exactly those worlds.
  Both were deleted, not tested.
- **Two reveals.** The client uncovered the ground itself and
  `TREK_MapContacts` did it again when the contact arrived, so deleting
  either changed nothing. The client's went.
- **The early return that looked redundant.** `S.land` refuses unloaded
  ground by itself, so the chunk test in `servicePlacement` reads as a
  duplicate. It is what stops the "no room" count running up, and warning,
  while nobody has been near her. The test now waits 400 ticks far away and
  reads the warnings.
- **She landed exactly on the point**, so "the mark moves to where she is"
  could not fail. The test grows a tree on the site first.
- **Every item was an annotated map**, to a mutation, until the test carried
  a hammer and one of vanilla's maps.

48 mutations, one at a time: 43 caught on the first pass, and the five that
were not are the list above.

---

## 8. Not yet seen in game

All of it. In a **new world** with *How the shuttle starts* set to
*Marooned*:

1. Right-click the ground on spawning: no Shuttlecraft entry.
2. Search a gas station's map rack and a few crates for an **Annotated Map**.
   This is the one piece that rests on an engine event nothing here had used
   before; the log line is `marooned: an annotated map is in a container`.
3. Read it: the note, the red mark on the map, the ground uncovered.
4. Travel to the mark. The log says `marooned: the shuttle is down at` as her
   ground loads. Her hull offers only *Board the shuttle*.
5. Go aboard: the note, and the menu back when you step out.
6. On a dedicated server: that a map made at the roll reaches a client's
   loot panel, and that the second player has no menu until they board.

Open questions for the author:

- **A latecomer and a ship overhead.** A player who joins after she is
  commissioned has no combadge until they board, and cannot board a ship
  that is overhead: a crewmate has to land her. That reads as the mode
  working, and it is one line to change if it is not.
- **The chance.** Fifty in a hundred per container that rolled a map. Too
  many or too few will show within one town.
- **The six.** Any site can be moved by editing `C.Maroon.sites` and running
  `python tools/maroon_sites.py`.
