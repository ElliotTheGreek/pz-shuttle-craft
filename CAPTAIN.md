# Captain — the woman in the chair

The working guide to Captain Titus: the *Adirondack*'s commanding officer, sat on
her bridge, whom a player can sit down with and ask what is going on.

`LORE.md` says what the shelf **remembers**, and `COMMS.md` says who is still
**talking**. This file is the one person aboard who can **explain**. Decided by
the author on 2026-09-28: **the captain is the primary way, besides the tapes and
the missions, that a player learns the story.** The tapes are testimony and
arrive out of order; the channel is Shepard living through it; the captain is the
one who can stand still and say where things stand.

The rules in `DEV_GUIDE.md` and `MULTIPLAYER.md` are binding as always. Read
*Rules that exist because they were broken* before starting.

**Specced and built 2026-09-28, and played the same day: "it's working well".**
The one fault found, sitting sideways in her chair, is fixed (section 8).

---

## 1. Who she is

**Captain Imogen Titus.** Human, commanding officer of the U.S.S. *Adirondack*.
She has not slept properly since February.

*Renamed from Vale on 2026-09-28, at the author's request.* Every mention of Vale
in `design/crew/*.txt`, `CREW.md` and `ITEMS.md` became Titus in the same change,
and the crew talk was regenerated. **The given name Imogen was kept from the old
entry and is the author's to change** (`K.Captain` in `TREK_Crew.lua`, and her
lines in `content/captain/HUB.json` and `WHO.json`).

What the crew already say about her (`design/crew/`), and so what she has to be
when the player finally meets her:

- She walks the decks at three in the morning, knocking on doors.
- She keeps the eleven on a padd by her chair and crosses nobody off.
- She stood by the transporter pad all night for a beam scheduled at noon.
- She put herself at the bottom of the replicator ration board.
- She knows all hundred and forty-one names.
- She ordered Shepard up in February and was refused, on an open channel.
- She listens to both sides for ten minutes, says both are right, and leaves.
- She "rates" the Q theory. It is on the file.
- A captain out of contact acts on her own authority, and she does.

### Her voice

- **Steady, dry, tired, and plain.** Short sentences. Command register without
  the speeches. She says *we* for the ship and *I* for decisions she made.
- **She owns her decisions.** She followed the observe-only order, she let
  eleven people stay on the ground, and she ordered Shepard up and lost.
- **She is a summariser, not a witness.** Shepard tells you how it felt. Titus
  tells you what the ship knows, what it does not, and what she would sign.
- **She is kind to the player** and never sure who they are (6).
- The dead below were people. She does not joke about them and does not preach.
- **She is not a quest-giver.** Asked what to do, she says what she would do in
  the player's place (4.10).

---

## 2. What she knows, and why she does not say all of it

**Titus has known the truth since the ninth of July.** Log six is explicit: the
*Adirondack*'s exobiologist worked out the Changeling and told Shepard before
Shepard beamed up, which is before the player's first day.

**Her gating is discretion, not ignorance.** She tells the player what the ship
knows for certain from the start, and declines the theory honestly -- *"My
exobiologist has a theory. I've read it. I've signed nothing."* -- until the
sandbox's gate opens. The question stays on her list so the player knows there
is more.

**Sandbox: *Captain tells the truth*** (`TrekShuttle.CaptainTruth`, decided by
the author 2026-09-28):

| setting | she tells it once |
|---|---|
| Only once Shepard has told it | the channel's `revealDone` |
| **When it is earned** (default) | `revealDone`, **or** this player has watched Shepard's last log (`watched:TREK_LogSix`), **or** this player has brought `C.CaptainTruthRescues` (2) of the crew home |
| From the first conversation | always |

`TREK_Captain.truth` is the whole rule. The tape and the rescues are asked of
**the player in front of her**, on the server's copy of them, so in co-op one
player can have earned it and another not.

**What she does not know, and never says:**

- **Tucker Gold, until `goldDone`.** After it she knows what Shepard told her.
- **That the Q theory is wrong.** She rates it. No line of hers says it was wrong.
- **Who the player is.** Never adjudicated (6).

`tools/gen_captain.py` enforces the first two: a line or option naming the
Changeling, the Great Link, the Founders, nanoprobes or the Collective must sit
in a tier that waits on `truth`, and one naming Tucker or the Douwd in a tier
that waits on `goldDone`, or the tree is not written.

---

## 3. What a player does

1. Beam across to the *Adirondack* (the shuttle's aboard menu) and take the lift
   to Deck 1. She is in the captain's chair.
2. Right-click her chair or the floor round it: **Speak with Captain Titus.**
   From across the bridge the option is there and greyed, with the reason.
3. The first time, she introduces herself and asks your name. Give it and she
   uses it; decline and she does not.
4. Her topics are listed. Those with something this player has not heard are
   orange, and the panel says **NEW**. Inside a topic, a question that leads
   somewhere new is orange too.
5. **Back to the topics** from any topic; **That's all, Captain** from anywhere.
6. If rescues have earned a rank, she gives it before anything else (4.13).

---

## 4. The topics

Every topic declares **tiers**, each opened by conditions; every node belongs to
one. The server never shows a node whose tier is shut and never offers an
option into one. A topic is NEW while it has an open tier this player has not
heard, which is the recap: when the story moves, the list shows where.

The gates are **the channel's own conditions** (`TREK_Comms.check`) plus a few
only a conversation in person can ask (`TREK_Captain.check`). **She adds no story
flags of her own** (5.4).

| topic | tiers |
|---|---|
| **Who are you?** | her, the ship now, how she is holding up |
| **Why is this ship here?** | the posting, Miri and the Uxbridge precedent, the order she followed |
| **What happened in February?** | the sabotage; nobody is coming; the transporters |
| **What happened down there?** | June; the dead; + the Doctor's half a signature (`scienceDone`) |
| **The eleven** | who stayed and why she let them; + some came home (`rescued>=1`); + names (`elevenDone`) |
| **Lieutenant Shepard** | before the first call she defers to Shepard; + after (`met`); + February's argument (`stayed`) |
| **Who did this?** | witnesses, the theories, Section 31; + Okafor's denial (`denialDone`, `pressed`); + **the truth** (`truth`) |
| **What is this world?** | a copy that grew by itself, the calendar, dilithium, the Q theory; + the recordings (`clueTold`); + Tucker Gold (`goldDone`) |
| **Is there a cure?** | the Doctor, a crystal, twelve hours; + Phlox's note (`archiveDone`) |
| **What would you do in my place?** | 4.10 |
| **What do you make of me?** | read from the uniform (6) |

### 4.10 What would you do in my place?

The in-fiction hint. Her answer is the first of these that is true:

| state | in substance |
|---|---|
| `shipDark` | your shuttle needs dilithium; open country, never in town |
| not yet told, log one not watched | Shepard's six logs are on the shelf by the television in her shuttle; start with the first (once, `me:toldTapes`; the author's request) |
| `carrying` a fragment | call Shepard; she can put it on tape |
| `distressLive` | one of mine has a beacon running; I'd go |
| not `probed` | launch a probe |
| not yet told | Shepard's field office in Muldraugh: the electronics shop, the stockroom, the breaker box (once, `me:toldStation`) |
| otherwise | sleep, eat, keep the core loaded |

### 4.13 Promotions

**Decided by the author 2026-09-28: the captain gives rank in person.** Rescues
still earn it (`TRAITS.md` 4.5: 1, 3, 5, 8, 11), but `TraitsServer.onRescue` no
longer sets the trait: it tells the rescuer *Captain Titus would like to see you
on the Adirondack's bridge*. The next time they speak to her -- on opening, or on
coming back to her topics -- she confers it: a **field commission** for somebody
with no rank (`HUB_COMMISSION`), a **promotion** for somebody with one
(`HUB_PROMOTE`). The rank is whatever the rescues are worth by then, so nothing
is lost by waiting. A Starfleet profession's starting rank is still given at
creation.

---

## 5. How it is built

### 5.1 The words

```
content/captain/HUB.json        opening, coming back, promotion, goodbye
content/captain/<TOPIC>.json    one topic each
```

`tools/gen_captain.py` reads them and writes `TREK_CaptainTree.lua` and the
`Print_Text_TREK_CAPT_*` keys (Print_Text.json's third writer, each owning its
own prefix). **It is its own generator rather than a mode of `gen_comms.py`**,
because the shapes differ -- a hub and spokes with tiers, where the channel is
timed calls with silence branches -- but it imports the channel's condition
vocabulary, flags and line limits, so the two cannot drift. It refuses:

- a `go` to nothing, an unreachable node, a route whose last arm is conditional;
- a topic node without a declared tier; `HUB`/`BYE` used as node ids;
- a condition neither she nor the channel answers; a `me:` mark nothing sets;
- the spoilers of section 2 outside their gates;
- a line over 70, an option over 60, a hub title over 32; option and title
  text that is not ASCII (a button upper-cases its label);
- `%1` (how she addresses you) or `%2` (your rank) in your options, `%3` (your
  name) in her lines.

A route arm may name several nodes, and one is picked at random: her greetings
and goodbyes vary that way.

### 5.2 Multiplayer: a private conversation, answered by the server

- **Every player has their own conversation, at the same time.**
- The client sends `captainTalk`, then `captainAsk` with the node it is answering
  and an option index, a topic, `back` or `bye`. The server checks the player is
  within `C.CaptainReach` of her chair on Deck 1, that the node is the one it
  last sent them and that the choice was on offer, then replies `captainSay`: the
  node, the options this player may take, which of them are fresh, and on the
  hub the topics with their NEW marks. Refusals are said (`captainFar`,
  `captainStale`).
- Sessions are the server's and unsaved; one ends on goodbye, on closing the
  panel, or when the player leaves her reach, dies or logs out.

### 5.3 What she remembers of each player

`C.CaptainKey` on the **server's** copy of the player: `heard` (topic:tier pairs,
bounded by her tree) and `marks` (`introduced`, `named`, `toldReveal`,
`toldStation`). Sent with each reply, never published.

### 5.4 What she changes

**Nothing in the story.** No channel flag, tape, item or scheduler entry; the
test snapshots the channel's store round a whole conversation. The one thing she
does is **give a rank the player has already earned** (4.13).

### 5.5 The body, and why the conversation does not need it

She is a crew member with a fixed look (`K.Captain`: human, command, grey bun)
and a pinned post: the crew director seats her in the first `captain_chair` on
`C.CaptainDeck` before anybody else can take it, whenever somebody is on the
bridge. She never leaves, is never counted against the deck's population, and
is kept out of every scene and bark: her words are her panel's alone. A captain
who has gone is seated again after `CS.CaptainRespawn`.

**The conversation is keyed to the chair, not the body** (`TREK_Captain.clicked`,
`C.CaptainMenuMargin`): a right-click lands on the floor under the cursor, and
the crew do not exist at all in a sandbox with no zombies. The test empties her
chair and talks to her anyway.

### 5.6 The surface

An LCARS panel in the Doctor's style: her portrait, her lines wrapped beside it,
a fixed pool of buttons shown, hidden and relabelled per answer and
re-registered on the controller each time. **The portrait is rendered** from
the body she is drawn with -- vanilla's female body, the command duty uniform on
its boilersuit rig, the bun from the white hair sheet tinted grey
(`tools/gen_captain_art.py`, raws in `design/art/captain/`).

### 5.7 Files

| File | What |
|---|---|
| `content/captain/*.json` | the words |
| `tools/gen_captain.py` | the generator and its refusals |
| `tools/gen_captain_art.py` | her portrait |
| `shared/TREK/TREK_CaptainTree.lua` | GENERATED: the tree |
| `shared/TREK/TREK_Captain.lua` | her chair, reach, conditions, the truth rule, walking the tree |
| `server/TREK/TREK_CaptainServer.lua` | sessions, handlers, marks, what was heard, promotion |
| `client/TREK/TREK_CaptainUI.lua` | the right-click and the panel |
| `shared/TREK/TREK_Crew.lua`, `server/TREK/TREK_CrewServer.lua` | her look, her post, kept out of scenes |
| `server/TREK/TREK_TraitsServer.lua` | a rescue makes a promotion due |

---

## 6. The player, again

**She never adjudicates who the player is.** She asks their name and uses it if
given. She reads their uniform the way anybody would. What they told Shepard is
not stored, so she cannot know it.

How she addresses them (`%1`): rank and surname once she has both, the rank
alone, their first name if she was told it, and otherwise *friend*.

---

## 7. Tests

- **`tests/test_comms.py`**: fifteen broken trees, one fault each, refused for
  that reason -- the Changeling in an ungated tier and Tucker Gold in an option
  among them; what is on disk is what the generator writes; every key has text
  and none is orphaned; the conditions the generator trusts are the ones
  `TREK_Captain.check` answers; the files are in the house layout.
- **`tests/test_multiplayer.py`**, `captain`: she is seated in her chair and
  stays through 2,400 ticks, never speaks a crew line while the bridge crew do,
  and is not counted against the deck; the option is at her chair, not across
  the bridge, and greyed out of reach; the first meeting, a name remembered,
  every topic NEW, heard and no longer NEW, NEW again when a tier opens and
  cleared when its question is asked; a stale node and an unoffered option
  refused out loud; the truth under all three settings, by tape, by rescues and
  by the reveal; a rescue that does not promote, a commission and a promotion
  given in person with the rank in her line; goodbye; the channel's store
  unchanged; the session ended by walking away; a conversation with nobody in
  the chair.
- `captain_multiplayer`: two conversations at once, each private; a name given
  by one is not the other's; the truth offered to the player whose server copy
  watched the log and not to one whose **client** did; an unoffered option
  refused; a commission on the server's copy, synced, told to its owner alone.
- **`tests/test_helm.py`**, `captain_panel`: every node of her tree drawn with all
  its options, inside the panel, labels fitting their buttons, her words inside
  the speech area, no raw keys, exactly the shown buttons on the stick; the hub
  with all topics and NEW.

**Nineteen mutations, one pass at a time, all caught.** One was missed on the
first run -- dropping the stale-node check -- because the only stale answer the
test sent was refused by the offered-option check as well: two guards covering
each other (DEV_GUIDE.md). The test now sends the case the node check exists
for, a stale answer whose option number is valid on the new node (a double
click landing on the next screen).

---

## 8. In game

**Played 2026-09-28**: the right-click, the panel and the conversation work.
**She sat turned 90 degrees in her chair**, and so would every seated crew
member. The cause is in the animation, not the seat: `Translation_Data`, the
bone the engine takes a turn from, is rotated a quarter turn in the standing
idle and not at all in `Bob_SatChair`, while the body bones match. Blending
from one to the other swung that bone 90 degrees, the engine read the swing as
the character turning, and the turn stuck, because the crew client faced a
body once on arrival. Measured, not guessed: each bone's rotation read out of
both animations with `tools/xskin.py`. Fixed twice over: the sit node takes
no deferred rotation or movement (`trekcrewsit.xml`), and a seated crew member
is held facing the way the seat looks on every update. **Not yet seen fixed.**

Still to see:

1. **She faces forward in her chair**, and the bridge officers in theirs.
2. **The panel on a Steam Deck.**
4. **A commission in person** after a real rescue, and the rank in the character
   panel afterwards.
5. **The truth** under the default setting, after watching log six.
6. **Two players** talking to her at once.
7. **A save from before her**: the first boarding of Deck 1 should seat her.

---

## 9. Decisions

Decided 2026-09-28 by the author: the name (Titus); the truth is a sandbox
option; rescues can earn it; the captain gives promotions.

Decided in building, and the author's to overturn:

- **Before the first call** the player can reach her, and she defers Shepard's
  story to Shepard (4.6's Shepard topic) rather than keeping her door shut.
- **Two rescues** earn the truth under the default.
- **The field station is on the hint list**, told once.
- **She is always in her chair**, with no night post at the ready-room desk: a
  walk between the two is the crew's least-proven behaviour, and the chair is
  where the menu is.
- **No overhead speech**: her panel is private.
- **Her look is fixed**: human, grey bun, skin 2. Imogen is kept as her given
  name.
