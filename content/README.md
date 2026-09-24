# content/ — every word the player reads in a tape or a call

All the writing lives here, and only here. The generators read it; no Python or
Lua file holds a line of it.

```
content/tapes/<TAPE_ID>.json    one file per VHS tape on (or issued to) the shelf
content/comms/<THREAD>.json     one file per Adirondack channel thread
```

After editing anything here, regenerate, then run the checks:

```sh
python tools/gen_tapes.py TrekShuttle/42     # tapes  -> TREK_Tapes.lua + Recorded_Media.json
python tools/gen_comms.py TrekShuttle/42     # comms  -> TREK_CommsTree.lua + Print_Text.json
python tests/test_comms.py                   # the tree, and that what is on disk is current
python tests/test_assets.py                  # every tape key, both ways
```

`gen_comms.py` **refuses** a thread with a broken link, an unreachable node, a
timed node without a silence branch, a flag nothing sets, or a line too long for
the screen, and names the node.

## What you may change freely

**Any `"text"` value**, and a tape's `display` / `title` / `subtitle` / `author` /
`extra`, and a thread's `title`. That is the writing. Everything else is
structure: voices, `codes`, `go`, `requires`, `sets`, node ids. Change those
only on purpose, because they are the game.

`notes` are the writing notes -- why a tape or a call exists, what canon it must
respect, what it must not do. Read them before rewording anything in the file.
They never reach the game.

## The rules a line has to keep

1. **A line is a shot.** Thirty to seventy characters on a tape or a channel line;
   **an option is a button, sixty at most**. A speech is several lines, not one
   long one. Line time on screen is proportional to length (LORE.md 2).
2. **Tokens survive.** `%1` is the holder's first name, `%2` the ensign most
   recently brought up or lost. A rewrite keeps every token it started with, and
   adds none. Only use `%1` after the player has given their name (`named`), or in
   the player's own options.
3. **Colour is the speaker**, so a line stays in its voice. `card` lines are title
   cards and status text (ALL CAPS on purpose); `note` lines are what the camera
   sees and nobody says.
4. **Testimony, not narration.** Every tape is somebody talking, or a camera left
   running. Nobody explains the plot to the viewer.
5. **Options are characterisation, not a quiz.** No option is correct. At least
   one in every node is what a tired, frightened person actually says -- usually
   shorter and ruder than the others.
6. **Never confirm who the player is.** She believes them or she does not.
7. **The canon is LORE.md 1a-1d.** Dates come from `gen_tapes.py`'s `NOW_YEAR`;
   Tucker Gold never names her and never files a date; there is no Q.

## Voice, and what to avoid

The lines were drafted fast and some read machine-written. The tells to take out:

- **Tidy triplets** ("the land, the river, the falls") and matched pairs used as
  rhythm rather than meaning.
- **Aphorism endings** -- a line that closes a thought with a quotable moral
  ("That's the whole problem with being a historian").
- **Announcing the feeling** instead of showing what the person does.
- **"It's not X. It's Y."** reversals, and "that's the point" / "and that
  matters".
- **Everybody sounding like the same clever person.** Shepard is a tired
  historian; the Doctor is vain and precise; Okafor is flat and careful; the
  ensign is scared and joking; Tucker Gold is old, plain-spoken, and a little
  formal.

A rewrite should be shorter or the same length, never longer, and should keep
the one fact the line carries.

## Rewording in bulk

`tools/text_units.py` turns this folder into one sentence per unit, and back:

```sh
python tools/text_units.py export units.jsonl            # every line, with its limits
python tools/text_units.py export units.jsonl --only comms
python tools/text_units.py import units.jsonl --dry-run  # what would change, and what is refused
python tools/text_units.py import units.jsonl            # apply
```

Each exported unit carries its `file`, `path`, `voice`, `max` length, the
`tokens` it must keep, and the lines either side of it for context. Put the
rewrite in a `new` field and import. A rewrite that breaks the length limit or
changes the tokens is **refused and listed**, and the file is left as it was.
Then regenerate as above.
