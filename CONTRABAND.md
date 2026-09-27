# Contraband

Built 2026-09-26. The working guide to what the off-watch crew keep in the
hideouts off the Adirondack's Jefferies tubes (`JEFFERIES.md`): four things
that hook you, one that punishes a second dose, the good bottles, a pot of
latinum and a holosuite reel -- and the Doctor's detox and a PADD's flashing
light for when it has gone too far.

**Nothing here has been seen in game yet.** Section 7 is what to check first,
and it needs a new world (the hideouts' crates are stocked once, ever).

---

## 1. What a player gets

| Item | Use | What it does |
|---|---|---|
| **Ketracel-White** | *Inject* | Endurance to full, fatigue -0.5, stress -0.5, panic to nothing, and a second wind for four hours. **Three doses and you are hooked.** A day without it: stress, panic and misery every ten minutes, and **endurance held under half**. Clean four days after the last dose. |
| **Felicium** | *Take* | The strongest pain relief in the mod (painReduction 25), unhappiness -30, stress -0.25. **Two doses and you are hooked.** Twelve hours without it and the "plague" comes: misery and food sickness, which **never goes past 35**. Clean three days after the last dose. |
| **Trellium-D** | *Inject* | To a **Vulcan**: unhappiness -60, boredom -50, stress -0.4 -- then, two hours later, a crash (panic +45, stress +0.35). Hooked at two. To **anybody else**: poison (food sickness +30, never past 40), no high and no habit. |
| **The Game** (Ktarian game) | *Play the Game* | One round: boredom -40, unhappiness -25, stress -0.2 -- **and each round is worth 8% less than the last** (down to 30%). **Four rounds and you are hooked.** An hour without it gets boring, fast. It lasts five days on its own. *Offer the Game to...* hands it to anybody within three tiles. |
| **Cordrazine** | *Inject* | Sickbay's stimulant: endurance +0.4, fatigue -0.3. **A second dose inside four hours** is the episode: panic +60, stress +0.4, misery. No habit. |
| **Kanar, Saurian brandy, Aldebaran whiskey** | *Drink* | Three more bottles for the stash shelf. Kanar is syrupy and strong, the brandy is the officer's drink, the whiskey is green. |
| **Latinum strips** | -- | The pot on the card table. Three per crate. |
| **Holosuite programme reel** | a tape | A Ferengi pleasure house's catalogue, dubbed off a display loop. Every programme is described, none is shown. Watch it, or transcribe it to a PADD. |

The cures:

- **The Doctor's detox.** A fourth button on his panel, *Detox (100 units)*.
  Every habit at once, for reserve units. Yourself at once; anybody else only
  if they say yes, like every other thing he does. His findings list the
  habits by name: *DEPENDENT: FELICIUM, THE GAME*.
- **The flashing light.** Right-click a PADD while the Game has hold of you:
  *Run the flashing-light program* (TNG "The Game": Wesley and Data broke it
  with a strobe). It clears the Game and only the Game.
- **Time.** Every habit ends on its own clock (`cleanAfter`), and a habit not
  yet formed is forgotten (`forgetHours`).

**Withdrawal never hurts the body.** Stress, panic, misery, boredom and a
capped food sickness: miserable, and never a wound or a death. That is a
decision, not a limit of the engine -- a zombie game already has enough ways
to die, and a drug that could kill you in a hideout would make the tubes a
place to avoid rather than a place to explore.

## 2. Where it is found

`A.Stock` in `TREK_Adirondack.lua`:

| Where | What |
|---|---|
| **stash_crate**, and each hideout's **stash_arms_*** crate beside it (two per hideout, three hideouts; the second also hides weapons, `ARMOURY.md` 7) | the old stash, plus one white, one felicium, one Trellium-D, one Game, three latinum strips -- and one holosuite reel (`tape = C.HolosuiteTape`) |
| **stash_shelf** (one per hideout) | the old shelf, plus kanar, Saurian brandy and Aldebaran whiskey |
| **medical_cart** (Sickbay, three) | the medical list, plus one cordrazine |

**None of it can be replicated** (`C.ReplicatorBlocked`, all nine ids). The
fiction is that a replicator refuses narcotics; the game is that the hideouts
are the only place any of it comes from.

## 3. How it works

```
the drugs     Food item, CustomContextMenu = TREK_Inject / Take, HungerChange 0
              -> vanilla's eating menu offers the word (doEatOption)
              -> ISEatFoodAction, whose complete() runs Eat() on the server
              -> TREK_Traits' wrap -> TREK.ContrabandServer.onAte -> S.dose / S.cordrazine
the Game      TREK_ContrabandUI menu -> TREKPlayGame (shared, global)
              -> complete() on the server -> S.play
every 10 min  S.service: crash, second wind, forget, clean, withdrawal, cravings
commands      gameOffer {to}   hand the Game to a player within C.GameOfferRange
              gameStrobe {}    the flashing light (needs a PADD, needs the Game)
              emhDetox {who}   TREK_Server, beside the EMH's other handlers
```

- **The record** is the player's mod data on the authority, under
  `C.ContrabandKey`: `{ [substance] = { doses, last, hooked, first, crashAt,
  boostUntil, nagAt, withdrew } }`, with cordrazine's last dose kept beside it
  (`record.cordrazine`) and never listed as a habit.
- **The client's copy.** A client's player never sees the server's write, so
  after every change of state the server sends `contraState` -- a summary of
  `{ doses, hooked, withdrawing }` per substance -- and the client keeps it
  under `C.ContrabandMirrorKey`. `TREK.Contraband.record` reads whichever key
  this machine owns. That is what lets the Doctor's panel grey *Detox*, and
  the PADD offer the light, from the player's own body.
- **Every stat change goes through `T.adjust`** and every word through
  `T.note` -- the traits' route, which applies on the server and mirrors to the
  owning client. `apply()` in the server file adds two ceilings on top: `limit`
  (an add never pushes the stat past it) and `cap` (the stat is held under it).
- **The only effect in a script is `painReduction`**, which vanilla's `Eat()`
  applies through `BodyDamage.setPainReduction`. Everything else is in
  `C.Contraband`, in the engine's own scales (unhappiness, boredom, panic and
  food sickness 0-100; stress, endurance and fatigue 0-1), so it can be tested.

## 4. Where everything lives

| What | Where |
|---|---|
| Every number | `C.Contraband`, `C.Cordrazine`, `C.Game*`, `C.EmhDetoxCost` in `TREK_Config.lua` |
| The shared rules (record, summary, habits, text keys) | `shared/TREK/TREK_Contraband.lua` |
| The authority (doses, rounds, service, commands) | `server/TREK/TREK_ContrabandServer.lua` |
| The Game's timed action | `shared/TREK/TREK_ContrabandActions.lua` (`TREKPlayGame`) |
| The menus, `contraState` | `client/TREK/TREK_ContrabandUI.lua` |
| The detox | `TREK_EMH.detoxRefusal`, `emhDetox` in `TREK_Server.lua`, the button in `TREK_EMHUI.lua` |
| Items, fluids | `media/scripts/trekcontraband.txt` |
| *Inject* | `Translate/EN/ContextMenu.json` (`ContextMenu_TREK_Inject`) |
| Icons | `tools/gen_contraband_icons.py`, raws in `design/art/contraband/` |
| The reel | `content/tapes/TREK_Holosuite.json` (`issued`, so it is never on the shuttle's shelf) |
| Stocking | `A.Stock` / `A.stockItems` in `TREK_Adirondack.lua`; the reel's `stockTape` in `TREK_AdirondackServer.lua` |

## 5. Engine facts this rests on

- **A Food item's menu word is `Translator.getText("ContextMenu_" + value)`**,
  read once when the item is made (`Item.InstanceItem`, bci 3801-3817), and
  vanilla's eating menu offers it in place of *Eat* for any food whose
  `HungerChange` is 0 (`ISInventoryPaneContextMenu.lua:466`, `doEatOption`).
  Vanilla ships `Take`, `Drink`, `Smoke`, `Sniff`, `Chew`; `TREK_Inject` is the
  mod's own, in the ContextMenu category.
- **`Eat()` applies a food's `painReduction`** through
  `BodyDamage.setPainReduction` (bci 457-468). Pain itself is recomputed from
  the body every tick, so setting `CharacterStat.PAIN` would do nothing.
- **`CharacterStat.FOOD_SICKNESS` is writable by ordinary play**: vanilla's
  tutorial sets it (`client/Tutorial/Steps.lua:629`). It is on `T.STATS` now,
  0-100.

## 6. What would have bitten you

- **A translation key that already exists is not yours to reuse.** The first
  draft put the detox's refusal under `IGUI_TREK_EmhClean` -- which is the
  panel's *No infection* label -- and rewrote it. The JSON writer warned; the
  refusal is `IGUI_TREK_EmhNoHabit`. Grep a key before you name one.
- **A key assembled from parts is invisible to `test_assets.py`**, and worse,
  its prefix *is* visible and fails as a key with no text.
  `"IGUI_TREK_Crave_" .. name` is a literal `IGUI_TREK_Crave_`. The keys are
  written out whole in `K.TEXT`.
- **A client can only offer the Game to somebody it can see.** The first
  two-client test gave each client only its own player and *Offer* never
  appeared. The engine's client holds every player near it; the test's
  clients do too now.
- **The Sickbay check was a whitelist.** `adk_fittings` failed any item in a
  medical container that was not on `C.Loot.medical`, which is right, and
  cordrazine is now Sickbay's own issue beside it.

## 7. Not yet seen in game, in the order worth checking

**Needs a new world**: the hideouts' crates are stocked once, and every save
made before this has its stash already.

1. **A hideout's crates.** The white, felicium, Trellium-D, the Game, three
   latinum strips and the reel; the three new bottles on the shelf. Icons at
   inventory size.
2. **Inject.** Right-click the white: the option reads *Inject* (not *Eat*,
   not `ContextMenu_TREK_Inject`), the hiss plays, and the endurance bar fills.
   If the word is raw, `ContextMenu.json` did not load.
3. **Three doses** of white, then sleep a day: the note, the shaking, and the
   endurance bar that will not go past half.
4. **The Game.** *Play the Game*: a progress bar, then the note and a drop in
   boredom. Four more: each note says it was not quite as good.
5. **The Doctor.** At the Adirondack's EMH (or the shuttle's): *DEPENDENT:*
   on the findings, *Detox (100 units)* live, pressed, and gone.
6. **The flashing light.** Play once, right-click a PADD: *Run the
   flashing-light program*.
7. **The reel.** Into a television: the programme reel plays, with its title.
8. **Two players**: *Offer the Game to...* from one to the other, and the
   Game in the other's inventory.
9. **Felicium's plague** and **Trellium-D** on a human and on a Vulcan.

## 8. How to change it

- **A dose, a habit, a withdrawal**: `C.Contraband` in `TREK_Config.lua`. Every
  field is described above the table. `python tests/test_multiplayer.py` with
  `TREK_ONLY=contraband,contraband_multiplayer` checks them all.
- **A new substance**: an item in `trekcontraband.txt` (Food, a menu word,
  `HungerChange = 0.0`), a row in `C.Contraband`, its name in
  `C.ContrabandOrder`, its three keys in `K.TEXT` and `IG_UI.json`, the id in
  the `C.ReplicatorBlocked` loop, and a line in `A.stockItems("stash")`.
- **Where it is found**: `A.Stock` / `A.stockItems`.
- **Icons**: `python tools/gen_contraband_icons.py` re-keys from the raws;
  `design/art/contraband/contraband_sheet.png` is what they were vetted on.
- **The reel's words**: `content/tapes/TREK_Holosuite.json`, then
  `python tools/gen_tapes.py TrekShuttle/42`.
