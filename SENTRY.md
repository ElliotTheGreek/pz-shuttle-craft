# The perimeter phaser sentry

A small Starfleet emitter you set down on the ground. Once armed it shoots the
nearest of the dead within five squares, one at a time, until its charge is
spent: lead a horde past it and it thins them out, and a big one gets through.

The author's brief (2026-09-29): "something I could drop on the ground, then I
let a horde group up behind me, then I run by the device and it kills all the
zombies, maybe it would have a limited number of charges or it would only do
a certain limited dps one zombie at a time so a big horde some would get past
it." It has both. Starfleet has no such thing on screen; the nearest canon is
the Dominion's Houdini mine (DS9, "The Siege of AR-558"), which is the other
design this could have been and is still open (section 7).

**Built 2026-09-29, not yet seen in game.** `DEV_GUIDE.md`'s *Rules that exist
because they were broken* and `MULTIPLAYER.md` apply to every line.

---

## 1. What a player gets

- **Three in the shuttle's armoury** (new worlds; build revision 34). The
  replicator knows the pattern from the first day, as it knows every item of
  the mod's, so an existing save makes them there.
- **Right-click it in your inventory: *Set down sentry (25 of 25 shots)*.** It
  goes on the square in front of you. Greyed, with the reason, where there is
  no room or aboard the shuttle, her decks or the field station.
- **It arms three seconds later**, so it does not open up on the horde while
  you are still in its way.
- **Then a phaser bolt every 0.6 s** at the nearest of the dead within 5
  squares on its own level, each one a kill. About a hundred a minute at most:
  a pack of twenty running through its five squares gets past it.
- **25 shots**, counted on the sentry itself. Its owner is told when it runs dry.
- **Pick it up again** like anything lying on the ground. It keeps its count.
- **Recharge it at a warp core** (the shuttle's, hers, the station's or an
  installed one): *Recharge sentry (250 units)* on its right-click, from that
  core's power, full again. Greyed away from one.
- Everybody nearby sees the bolts and hears the shots.

## 2. Where everything lives

| What | Where |
|---|---|
| Every number | `TREK_Config.lua`, section *The perimeter phaser sentry* |
| The rules both sides read: its charge, the square in front, why a square refuses | `shared/TREK/TREK_Sentry.lua` |
| Setting down, the list, firing, recharging | `server/TREK/TREK_SentryServer.lua` |
| The right-click, the notes, the shot's sound | `client/TREK/TREK_SentryUI.lua` |
| The bolt | `client/TREK/TREK_PhaserFX.lua`, `FX.boltAt` |
| The item and its model block | `media/scripts/trekshuttle.txt`, `item TrekSentry`, `model TrekSentryModel` |
| Mesh, texture, icon | `tools/gen_sentry.py` writes `models_X/TREK_Sentry.x`, `textures/TREK_Sentry.png`, `textures/Item_TREK_Sentry.png`; the sheet it was judged on is `design/art/sentry/sentry_sheet.png` |
| In the armoury | `TREK_InteriorLayout.lua` (`special` "sentries"), `TREK_Build.lua`'s SPECIAL |
| Words | `IG_UI.json` `IGUI_TREK_Sentry*`, `ItemName.json`, `Tooltip.json` |
| Tests | `tests/test_multiplayer.py`: `sentry()`, `sentry_multiplayer()` |

## 3. How it works

- **The charge is on the item** (`C.SentryChargesKey` in its mod data; absent
  is full), so it goes wherever the sentry goes.
- **Setting down is a command** (`deploySentry {id}`). The server finds that
  item in its own copy of the player's inventory by id, takes it out and
  **counts** that it went (a Remove that did nothing would lay a copy and keep
  the original), puts the **live item** down with
  `AddWorldInventoryItem(item, ...)` on the square in front of the player as
  *it* sees them, writes an id on it and lists it in `TREK_Sentries` global
  mod data, which is the server's alone.
- **Firing** is the server's, five ticks at a time: each listed sentry whose
  ground is loaded is looked for on its square by that id. Gone means picked
  up, and it leaves the list. Otherwise, armed, charged and due, it takes the
  nearest living zombie on its level within range that is not `useless` (the
  Adirondack's crew are pacified bodies that cannot be hurt, and a sentry
  would fire at one for ever).
- **A shot is the engine's own server-side hit.** `IsoTrap.explosion` hits
  every character in a blast with `IsoMovingObject.Hit(weapon, attacker,
  damage, false, 1.0)` on the server (bci 121). `IsoGameCharacter.Hit` is the
  whole pipeline a gunshot runs (`processHitDamage`, then `hitConsequences`,
  where a zombie dies), and `IsoZombie.Hit` tells the clients of a death on a
  server (bci 233-254). The weapon is a phaser, made once; the attacker is the
  sentry's owner when they are online, for the kill, and otherwise the cell's
  stand-in (`getFakeZombieForHit`), as a trap's is. `C.SentryDamage` 100 is a
  kill.
- **The bolt** goes to every client as `sentryShot` (no weapon event fires for
  a shot nobody holds), and `FX.boltAt` draws it from the sentry's emitter,
  `C.SentryEmitterZ` up, in the phaser's colour. The zap is played on each
  machine within 25 squares with `playSoundLocal`, the phaser's own rule.
- **Recharging** (`rechargeSentry {id}`) needs the server's copy of the player
  at a core (`Power.inReachOf`) and goes through the ledger
  (`Energy.energize`), which bills the pool the command runs under: the
  core they are standing at. The item's mod data goes back with
  `syncItemModData`.

## 4. Changing it

All in `TREK_Config.lua`: `C.SentryCharges` (25), `C.SentryShotMs` (600),
`C.SentryRange` (5), `C.SentryDamage` (100), `C.SentryArmMs` (3000),
`C.SentryRechargeCost` (250), `C.SentryMax` (12 set down per server),
`C.SentryIssue` (3). The look: `tools/gen_sentry.py`, re-run, look at the
sheet.

## 5. Testing

```sh
TREK_ONLY=sentry,sentry_multiplayer python tests/test_multiplayer.py
```

**`sentry()`**, single player, through the right-click: set down out of the
pocket onto the square in front; silent until armed; a pack of eight down one
at a time, one per interval and the nearest first; never one beyond range or
one of the crew; the bolt drawn from the sentry; its count spent off the item
and a note when dry; picked up, off the list with its count; the recharge
greyed and refused away from a core, and at one full again for its price;
refused aboard; a ration pack's id refused; and a removal that does nothing
never leaves two.

**`sentry_multiplayer()`**: alice's client asks, the server sets it down and
fires, the kill reaches both clients, both see the bolt, and neither client
edits the world.

**Nineteen mutations, one at a time, all caught**, three only after tests
were written for them (the stuck removal, another item's id, the bolt's
start), and one of those only after the harness was fixed: its search text
occurred twice in `TREK_PhaserFX.lua` and it had mutated the cutting beam's
line instead of the bolt's. *A mutation that does not apply proves nothing*
has a twin: one that applies to the wrong place proves nothing either.

## 6. Not yet seen

All of it. What to look at, in a fresh world: the sentry in the armoury, its
look on the ground, setting it down and picking it up, the bolts and the
zap, whether the dead actually fall (the engine's hit pipeline from the
server; single player is the first question), and a horde led past it.

## 7. Open

- **Line of sight.** It shoots through walls. Five squares is short, but a
  sentry set down beside a house will fire into it.
- **The Houdini**, the canon Dominion mine: plant it, it phases out (the
  transporter's sparkles), and it comes back and blows when the dead are near.
  One blast, a wide radius; the photon torpedo's explosion is the machinery.
