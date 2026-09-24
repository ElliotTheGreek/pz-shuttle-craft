# Comms — the Adirondack channel

A text conversation with the ship in orbit, and the scheduler the rest of the
mod has been waiting for.

`LORE.md` says what the shelf **remembers**. This file says who is still
**talking**. **`PADD.md` 12 is the surface this runs on** and the two files have
to be read together: the content, the scheduling and the multiplayer authority
are here; the screen is there. There is no console fitting — the PADD is the
terminal.

The rules in `DEV_GUIDE.md` and `MULTIPLAYER.md` are binding as always: the
server owns the channel, its state and anything it hands out; a client asks and
displays. Read *Rules that exist because they were broken* before starting
anything below — section 2 exists entirely because of them.

Specced 2026-09-24 and **built the same day**, the whole of section 7: the
channel, its scheduler, every thread in 6.1-6.3 and the clue chain. First contact
has been seen in game. Section 9 is what was built and what was decided while
building it; read it before changing anything here.

---

## 1. What this is, and the honest cost

Two features wearing one coat.

**An interactive dialogue system.** Shepard is alive aboard the *Adirondack*
(`LORE.md` 1b), the ship cannot leave, and it can still transport. She is the
mod's only living voice; the tapes are its dead ones. Until now the player has
had no way to answer either.

**The mod's scheduler.** `LORE.md` 6 parks three things the shelf cannot do — a
tape that appears on commissioning, a tape that appears once the Doctor is up,
and a tape that arrives on its own — and it names the fix: *a bounded record of
which tapes the ship has issued, and a service pass that adds one when its
condition is met and has not been met before.* **That is this feature's trigger
engine, and it is the same object.** Build it once and `LORE.md` 10's step 5
falls out for free.

**And the cost, stated plainly, because the shelf spoiled us.** The tape shelf
was the cheapest large feature left in the project because Build 42 already had
a media player, a subtitle renderer, a progress store, a timed action and a
multiplayer sync path. **None of that is true here.** This is a new UI, a new
state machine, new persistence and a new multiplayer path, plus more writing
than the entire shelf. It is the most expensive thing in the project by a wide
margin. It is worth building, and it wants a vertical slice long before it wants
content — section 7.

### What the channel buys that a tape cannot

- **It can say the player's name.** A media line is static text and cannot
  interpolate (`LORE.md` 5). The PADD can, which is why the channel is the right
  home for anything addressed to *this* person.
- **It can be answered.** The shelf is testimony. This is a conversation, and
  the player's half is the only place in the mod where they get to decide who
  they are — see 6.1.
- **It can be missed.** A tape waits for ever. A hail does not, and a missed
  call is the cheapest source of consequence the mod has ever had access to.
- **It knows what the player has done.** Eleven crew are on the ground
  (`ROADMAP2.md` 1.7). The channel is where a rescue stops being a counter and
  becomes somebody who answers by name.

---

## 2. Multiplayer, first, because it is the hard part

A conversation is **shared mutable state with a turn order**, which is the worst
shape this project has tried to synchronise. Decide all of it before writing a
line of dialogue.

**The server owns the conversation.** One authoritative state per ship, not per
player: current node, flags, pending and fired calls, cooldowns. A client sends
*"I chose option 3 of node X"* and the server validates that against the node it
believes is live. A client naming an option that is not on the current node is
**refused, not trusted** — that is the whole of `MULTIPLAYER.md`'s thesis
applied to a menu.

**One player holds the channel: whoever answers first, from wherever they are.**
They pick the options. Every other PADD shows the conversation live and
read-only, with a visible `SPEAKING: <name>` so nobody spends thirty seconds
wondering why their buttons are dead. Note what the PADD changes: the holder is
not whoever is nearest a console, because there is no console. The alternatives were considered and rejected: *anybody may
pick any option* is a griefing surface, and *a designated comms officer* is a
role system the mod does not have and should not grow one for this.

**Every timed node has a silence branch, and it is a feature.** If the holder
does not choose inside the window, the call proceeds as though they said
nothing. That stops an idle player holding the channel hostage — and it is
better writing anyway, because on a comm channel **silence is an answer**, and
Shepard reacting to a long pause is more interesting than a menu waiting for
ever.

**The four cases that have to be answered before anything is built:**

| case | resolution |
|---|---|
| holder logs out mid-call | channel releases; current node stands; next interactor becomes holder |
| holder is out of contact | there is no range check — a PADD reaches orbit. Losing the PADD releases the channel |
| a player joins mid-call | sees the live call and **the whole history** (decided 2026-09-24: the record is the ship's) |
| two clients answer in one tick | first to the server wins; the second is refused and told why |

**Nothing is stored client-side.** Not the transcript, not the flags, not the
"have I heard this" state. The shelf could lean on the engine's per-player media
memory; this has no such thing and must not invent a client-side one.

---

## 3. The data, and why it is generated

Follow `tools/gen_tapes.py` exactly. It is the pattern that worked, and for the
same reason: **two files have to agree, so one program writes both.**

`tools/gen_comms.py` is the source of truth and emits

- the Lua dialogue tree the server reads, and
- the translation entries the panel displays,

with **every key derived from node id plus option index**, so a duplicate key is
not expressible rather than tested for. This is the single most valuable thing
carried over from the shelf and it is not negotiable.

### Node schema

    id          TREK_COMM_<thread>_<n>   namespaced — FileGuidTable.mergeFrom taught us why
    speaker     name key + r,g,b         colour is the speaker, same rule as the tapes
    lines[]     30-70 chars each         a line is a shot, not a paragraph
    options[]   text / requires / sets / goto
    timeout     seconds (optional)       requires a silence branch if present
    onEnter     flags, effects, grants   optional
    terminal    ends the call

Two rules inherited wholesale from `LORE.md` 4, because it is the same medium
read by the same person in the same chair: **a line is a shot, thirty to seventy
characters**, and **colour is the speaker** — two voices and a caption colour is
plenty, four is soup.

One rule that is new: **the player's options are characterisation, not a quiz.**
No option is correct. At least one in every node should be the thing a tired,
frightened person actually says, which is usually shorter and ruder than the
others.

### Generator-time validation

Every one of these is a failure the generator refuses to emit, not a test that
runs later:

- every `goto` resolves to a real node;
- no node is unreachable from an entry point;
- no `requires` names a flag that nothing anywhere `sets`;
- every node with a `timeout` has a silence branch;
- every thread terminates;
- no line exceeds the character budget.

---

## 4. Triggering — the scheduler

**Two clocks, and the choice matters.**

Time is counted in **days since the ship was commissioned**, not days since the
world started. A player may not find the shuttle until day 40, and *"two weeks
later"* has to mean two weeks of theirs. This is the same reasoning that makes
`ROADMAP2.md`'s commissioning the mod's real day zero.

**First contact is one week after commissioning, and that is deliberate.** The
shelf comes first. A player gets seven days to work through twelve tapes, or to
ignore every one of them, before a living voice arrives — so the archive is
something they found rather than something they were handed on the way to the
plot. It also means Shepard's first call lands on somebody who may already know
most of what she is about to say, which is the next point.

**Overlap between a tape and a call is good, and the channel should not avoid
it.** An earlier draft of this file proposed that a call never re-explain a log.
That was wrong and is struck. Shepard is a person who has been alone in orbit for
months, and people repeat the things that matter to them; a player who watched
the logs gets the pleasure of recognition, and a player who did not gets the
story. **Write for the second and let the first enjoy being ahead.** The only
thing to avoid is a call that is *nothing but* a log read aloud.

**A call fires when** `earliestDay` **and** `requiredFlags` **and not**
`alreadyFired`. Flags come from things the mod already knows: ship commissioned,
EMH online, dilithium located, crew recovered (count, *and which*), tapes
watched.

**The issue record is the whole of `LORE.md` 6.** One bounded server-side record
of what this ship has fired — calls and tapes in the same table — and one slow
service pass that checks conditions. Note the constraint `LORE.md` 6 already
identified: it must not live in the ship state that `Ship.commit()` transmits
whole (*State that is transmitted whole cannot hold a list that grows*), and the
honest first move is to **measure** rather than argue, because a few dozen
booleans may well be small enough that it can.

**Incoming calls announce and open a window.** Miss it and it becomes a **missed
call with its own, worse follow-up.** Do not let a missed call silently retry;
the consequence is the point.

**Outgoing hails are gated by flag and cooldown**, and most of the time the
honest answer is that nobody picks up. That is not a stub — it is the situation.

**One consistency check that lands in the mod's favour.** `LORE.md` 1b
establishes that long-range comms have been dark the whole time. The
*Adirondack* is in orbit. Short-range works; Starfleet does not. **The feature
is possible for exactly the reason the situation is hopeless**, and no
retrofitting is required to make those two facts sit together.

---

## 5. The surface

**It is the PADD.** See `PADD.md` 12.4, which owns this entirely: full-screen,
three views (channel, history, library), navigable on a Steam Deck, and readable
anywhere on the map because the *Adirondack* is in orbit and a PADD is not a
fixed console.

Two consequences that belong here rather than there:

- **There is no comm panel in the cabin**, and the question of where to put one
  is closed. Nothing new is built into the hull for this.
- **The history is replayed, not stored** (`PADD.md` 12.2). The record holds the
  node ids visited and the options taken; the text is regenerated from the
  generated tree at display time. That is what keeps a growing shared list out of
  transmitted state, and it is the single most important implementation decision
  in either document.

---

## 6. The threads

Shepard is the primary voice. The **EMH** is the second, and the **Section 31
officer** is the third. `LORE.md` 1b's six logs are the dead version of this
story; these are the parts of it that are still moving.

### 6.1 First contact — and the one that matters most

She is astonished that anyone is aboard her shuttle. It establishes the three
facts the player needs: she is alive, the ship cannot leave, and **they can still
transport.**

**And this is where the player decides who they are.** The options let them claim
to be a native of this county who found a strange vehicle, or a Starfleet
officer, or refuse to say. **The mod never adjudicates it.** She believes them or
she does not, the dialogue accommodates both for ever, and no lore object
anywhere confirms an answer — because the player has already done this in their
head, and the mod's job is to not contradict them.

### 6.2 The rest of the spine

| thread | gate | what it is |
|---|---|---|
| **Come up / stay down** | after 6.1 | she explains why she stayed. The player can argue, and should be able to lose the argument. |
| **The eleven** | after 6.1 | coordinates for crew on the ground. Named. Later dialogue knows which came up and which stopped answering. |
| **The science** | EMH online | the graft — morphogenic markers plus something he cannot place. He is reading half a signature. |
| **The archive** | late | Phlox's omicron-radiation note, 2153, filed and unread for two hundred and fifty years. Paperwork, not a miracle. |
| **The denial** | after the science | `LORE.md` 1b entry five, now interactive. The player may press the Section 31 officer or let it go. |
| **The reveal** | late | the rogue Changeling, the nanoprobe graft, and the plan for the Federation worlds. |
| **The clue chain** | see 6.3 | six Tucker Gold fragments, found by probe, converted to tape. The only thread that hands the player an object. |
| **Tucker Gold** | with the chain | what this planet *is*. Starfleet's Q theory, honestly held, then dismantled by the fragments. |
| **The quiet path** | any time | the player tells her to stop calling, and **she does.** The shelf stays the only voice. |

### 6.3 The clue chain, and the conversion

`LORE.md` 1c is the story; this is the machinery. **It is the only thread that
hands the player an object, and the only place in the mod where the channel
creates a tape.**

1. **A probe finds a site.** `PROBES.md`'s sweep gains a third result beside a
   crystal and a survivor: **a clue**. Same system, one more outcome.
2. **The player recovers a fragment** at the site — an item, holographic, three
   hundred years old, and *losable*: it stays on a body like anything else.
3. **The player tells Shepard.** A short thread, and her line is the hinge:
   *"Hang on. I can put that on magnetic tape."*
4. **A tape appears in the shelf**, for everyone, permanently.

**Why this works without new machinery.** `LORE.md` 1a already established that
she dubs *holos flattened to two dimensions* onto tape because that is what the
television takes — written before this feature existed, which is the strongest
evidence the framing was sound. The conversion is not a contrivance; it is the
thing she has been doing the whole time.

**Six fragments, and the conversion is what the player is racing.** A fragment in
a pocket can be lost; a converted tape cannot. That gives the channel a reason to
be urgent without a timer, and it gives a death on the way home a real cost that
is not the player's inventory.

**Ordering.** The fragments are Tucker's life in order (`LORE.md` 1c), but probes
find sites in whatever order the map offers. Two options and the second is
better: refuse conversion out of order (bad — it punishes exploration), or **let
them arrive in any order and have Shepard say so**. She is a historian; a
historian handed document five before document one says which one it is and what
is still missing. That is free characterisation and it removes a constraint from
the probe system.

**Starfleet's Q theory dies here.** It is on the file, everybody sensible holds
it, and no single fragment refutes it — the *accumulation* does. Do not write a
node where Shepard announces the Q theory is wrong. Write the nodes where she
stops mentioning it.

---

That last row is not a courtesy. It is cheap, it respects the player, and a mod
whose premise is *nobody is coming* should be able to honour somebody who
decides they would rather it stayed that way.

---

## 7. Order of work

1. **One call, end to end.** The panel, the server state, one three-node thread
   with a timed silence branch, persistence across save and load, and the
   multiplayer path exercised with two clients. No content beyond that thread.
2. **The mutations**, run one at a time, in the style `LORE.md` 10 step 1 used —
   which caught four of four:
   - drop a `sets` — does the later gate still open when it should not?
   - orphan a `goto`;
   - fire a call twice — does the issue record hold?
   - two clients answer the same node in the same tick;
   - the holder logs out mid-call;
   - a timed node with its silence branch removed.
3. **The issue record generalised** to tapes, which closes `LORE.md` 6 and
   unlocks tier 3's gating and every converted fragment.
4. **6.1 written in full**, because it is the thread that establishes the
   player's own identity and everything else references it.
5. **The spine**, alongside `ROADMAP2.md` 1.6 and 1.7, because the crew thread
   and the rescue mechanic are the same feature seen from two directions.
6. **The clue chain** (6.3), last, because it needs the issue record, a probe
   result and the fragment item — and because it is the only part of the story
   that cannot be told without all three.

Step 1 is the only step that can sink this, and it is not a writing problem.

`tests/pz_sim.lua` will need a comms stub the way it needed a radio. The gap to
design for up front is the one the shelf hit: **the stub has to be able to
express a call that exists with no dialogue attached**, because that is the
failure that matters and the harness could not previously express its
equivalent.

---

## 8. Open questions

Every question below is answered in section 9.

- ~~**Where the panel goes.**~~ **Closed** — there is no panel. The PADD is the
  terminal (`PADD.md` 12.4).
- **Whether the issue record fits in transmitted ship state**, which is a
  measurement and not an argument (4). Note the history itself is *not* the
  problem: it is node ids, and it is a render (`PADD.md` 12.2).
- **Whether a call should be able to interrupt the television.** The engine
  synchronises a playing tape to the room; a hail arriving mid-tape is either
  excellent or infuriating, and only play decides which.
- **Whether missed calls accumulate or collapse.** Three missed hails should
  probably become one worse conversation rather than three queued ones.
- **Whether the player's claimed identity (6.1) is stored at all.** It is
  tempting to set a flag. The stronger answer may be that the mod never writes
  it down, and every later node offers both readings.
- **Voice colours.** Shepard, the EMH, Section 31 and the named crew is already
  four, which section 3 calls soup. Likely answer: the crew share a colour and
  are distinguished by name. **Tucker Gold needs one too** and he is a seventh
  voice — the fragments are tapes rather than calls, so `gen_tapes.py`'s `VOICES`
  is where that is decided, not here.
- **What a fragment is, as an item.** Weight, icon, whether it is destroyed by
  the conversion or kept as a memento. Leaning: consumed, because a converted
  tape is the permanent form and two copies of the same evidence is clutter.
- **Whether a second player can convert a fragment somebody else found.** The
  channel is shared and the shelf is shared, so probably yes and it does not
  matter who carries it — but it is the kind of thing that wants saying out loud
  before two people argue about it in a session.

---

## 9. As built (2026-09-24)

### Where things live

```
tools/gen_comms.py                    the generator and its checks
tools/comms_vocab.py                  say / opt / branch / node / thread
content/comms/*.json                  the writing -- one file per thread (content/README.md)
shared/TREK/TREK_CommsTree.lua        generated: the tree the server walks
shared/Translate/EN/Print_Text.json   generated: every line, option and name
shared/TREK/TREK_Comms.lua            the two stores, conditions, the renderer
server/TREK/TREK_CommsServer.lua      scheduler, call, holder, clock, handlers
client/TREK/TREK_PaddScreen.lua       the surface (PADD.md 12.8)
tests/test_comms.py                   the generator refuses what it should
tests/test_multiplayer.py             comms, comms_missed, comms_multiplayer,
                                      comms_story (the whole campaign)
```

**Why Print_Text.** A mod cannot add a translation category: `Translator.BY_NAME`
is a fixed list and a key is routed to its map by prefix (`getTextInternal`).
`Print_Text_` is the category vanilla keeps printed text in, this mod had no file
for it, so `gen_comms.py` owns it outright -- one writer per file, the rule
`gen_tapes.py` already follows for `Recorded_Media.json`.

### The two stores

`C.CommsKey` is the live channel: the call, flags, what has fired, misses,
counters, the issue record. Published on every choice. `C.CommsLogKey` is the
history, published when a call ends. A row is a thread id, a day, the holder's
name and the steps as `{ n = node, o = option }` -- `o = 0` is silence. The text is
rendered from the tree at display time, so fixing a line fixes every transcript.
Bounded at `C.CommsLogMax` rows.

### The call

- **Ringing** for `C.CommsRingHours` game hours; then it is **missed**.
- **Answered** by whoever gets to the server first, carrying a PADD and allowed to
  use the ship. The second is refused by name (`commsHeld`).
- The server walks the tree. On entering a node it applies the node's flags, any
  tape it issues and any fragment it converts, records the step, and publishes
  **the indices of the options this holder may take** (`call.avail`). The client
  shows exactly those, because the questions behind them -- what the holder
  carries, what they have watched -- are only answered truly on the authority.
- A choice is accepted only for the live node and an offered index; anything else
  is `commsStale`.
- **Silence**: a node's `timeout` is seconds of play on the authority's tick, each
  tick capped at `C.CommsMaxTickSeconds` so a pause or a hitch cannot eat an
  answer. When it runs out the call takes the silence branch and records `o = 0`.
- **The holder lets go** when they go offline, die, stop carrying a PADD, or sit
  for `C.CommsIdleSeconds` without choosing. The call keeps its node and anybody
  can take it (`commsAnswer` on a live call with no holder); the options are asked
  again for the new holder.
- A live call nobody holds for a ring's length is **cut**, and counts as missed.

### The scheduler

Every game minute, outside any loaded-ground branch. **Day zero is the first
boarding** (decided): `TREK_CommsServer.commission` sets it the first time the
cabin is built, and ROADMAP2 1.6's cold start will change that one function.

- An incoming thread rings when its `day` has come, the thread named in `after`
  has run and its hours have passed, its `requires` hold and its `forbids` do not,
  it has not fired (unless repeatable), its retry time has passed, and the
  channel has been quiet for `C.CommsGapHours`. First eligible in priority order.
- **The sandbox's "When the Adirondack first calls"** (straight away, a day, three
  days, a week, two weeks) shifts the whole calendar, so later threads keep their
  spacing. "Straight away" is also how a player reaches the channel in a fresh
  world without a debug console.
- **A missed story thread comes back worse, rather than again.** It rings after
  `C.CommsRetryHours` and opens on the entry for that many misses (`01`, `01M`,
  `01MM`...). Collapse is built in: one thread, one follow-up, never a queue
  (section 8's open question).
- A missed **repeatable** (`THANKS`, `LOST`) lets go of the event it was waiting
  on, so the next rescue rings afresh.
- **Hails.** The first hail thread whose conditions hold picks up; a repeatable
  hail has a cooldown, and otherwise nobody answers (`commsNoAnswer`, and a hail
  cooldown). `QUIET` is repeatable with a day's cooldown -- not repeatable, a
  player who once said "wrong button" would have lost the quiet path for good.

### Tapes the channel issues (LORE.md 6)

The issue record is `issued` and `pendingTapes` in the live store.
`TREK_Build.deliverTapes` puts each owed tape on the shelf the next time the cabin
is loaded, reads each one back off the container before it stops being owed, and
runs as a build phase and on the service tick -- so it reaches existing saves.
`gen_tapes.py` marks such a tape `issued`: registered like any other, not stocked
on the first build. `tests/test_comms.py` fails if a tape the story issues is also
shelf stock.

The first rescue issues `TREK_EnsignLog` (LORE.md 5, #17). Each conversion issues
its fragment's tape.

### The threads, as written

| thread | rings | what it is |
|---|---|---|
| `FIRST` | day 7 (sandbox) | 6.1: she is alive, the ship cannot leave, they can transport, and who the player is -- never adjudicated, never stored |
| `THANKS` / `LOST` | a rescue / a lost beacon | repeatable; she says the ensign's name (`%2`) |
| `CLUE` | a probe finds a clue site | the holo emitter, and the Q theory on file, respectfully |
| `STAY` | after FIRST, 40 h | why she stayed down; the player can argue and lose |
| `ELEVEN` | after STAY, 40 h | the crew on the ground; routes on whether anyone has come up |
| `SCIENCE` | after ELEVEN, 30 h | the graft, half a signature -- off the shuttle's Doctor if he is up, off the rescued crew's samples if not |
| `DENIAL` | after SCIENCE, 36 h | Okafor; press or let it go |
| `ARCHIVE` | after DENIAL, 36 h | Phlox's omicron note: paperwork, not a miracle |
| `REVEAL` | after ARCHIVE, 48 h | the one who left the Link, and what it is rehearsing for |
| `GOLD` | all six converted | his name, and "the place was made, the people weren't" |
| `GRIEF` | REVEAL and GOLD both done | two griefs; the last call |
| `CONVERT` | hail, carrying a fragment | one conversion per call |
| `QUIET` / `RESUME` | hail | the quiet path, both ways |

**Nothing waits on a system the player might never build.** The science was
specced behind "EMH online"; it routes instead.

**The Q theory dies of accumulation**, as 6.3 asks: `CLUE` states it, the first
conversions mention it, the later ones do not, and `GOLD` never says it was wrong
-- she says she will write down what he said and let them decide.

### The clue chain (6.3)

- `C.ContactKinds.clue`, with its own hexagonal map symbol. Once `met` is set, a
  probe that finds something finds a clue site `C.ProbeClueShare` of the time,
  while any fragment is owed. Never the first probe of a save.
- **A fragment is owed while it is not on tape and no live contact points at
  one** -- not "while nobody has picked it up". A fragment lost on a body can be
  found again by a later probe, so the chain cannot be soft-locked, and a death on
  the way home costs time rather than the story (section 8's question about
  losing one). The fragments are in any order and she says which one it is.
- The ship puts the fragment on real ground when a player loads it, exactly as a
  crystal; the tricorder plots it as its own shape with its own line.
- `CONVERT` converts one fragment per call, chosen by what the holder carries,
  taken out of their pockets on the authority at that moment. The first time she
  says the line: *"Hang on. I can put that on magnetic tape."*
- **Anybody can convert a fragment somebody else found** (decided). The fragment
  is consumed (decided).

### What play and the harness found

- **The first ring said she had never called.** A ringing call has no lines yet,
  and the empty box fell through to the idle text. Found in the first play-test,
  fixed, and the harness now fails it.
- Section 8's remaining questions were decided: the claimed identity is not
  stored; a hail does not interrupt the television; missed calls collapse; the crew
  share one colour (blue); Tucker Gold is `gen_tapes.py`'s `tucker` voice, in the
  fragment's own cyan.

