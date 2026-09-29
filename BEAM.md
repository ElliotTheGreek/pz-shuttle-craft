# The transporter, as it is seen

Every beam in the mod is now a column of sparkles over the character, on
every screen that can see them: it builds up where they stand, shimmers, and
fades where they stood once they have gone; and where they arrive it is there
at full strength the moment they are, shimmers over them, and fades off them.

**Built 2026-09-29, and played the same day**: the author tested it and it passed. `DEV_GUIDE.md`'s *Rules that
exist because they were broken* and `MULTIPLAYER.md` apply to every line.

---

## 1. What a player sees

- **Leaving:** the column builds up over them in about a third of a second,
  shimmers for the second and a half the transporter takes, and when they go
  it stays where they stood and fades in under half a second.
- **Arriving:** a column at full strength on the spot, which shimmers for
  0.8 s and fades, leaving them standing there.
- **Everybody nearby sees both**, for every player.
- **Which moves:** every beam -- up, down, a landing with the crew, the way
  home from a landing with no room, to and from the Adirondack, the lift at a
  resolved lock, out to a raid and home. Not the hatch, the turbolift or the
  field station's lift, which are walks (`C.BeamFxKinds`).
- **The character is not faded under it.** See section 4.

---

## 2. How the frames were made

Seven frames, 128x256, in `media/ui/TREK_Beam_00..06.png`: 00-03 are the
shimmer, 04-06 the fade. Leaving plays the fade backwards to build up.

All seven were drawn by Gemini through the FlowDot `gemini-image` toolkit
(`gemini-3-pro-image-preview`), and the raws are in `design/art/beam/`:

1. **The peak frame** (`frame_00.jpg`) from `generate-image`: a tall column
   of pale blue-white sparkles on pure black. Two tries were rejected and are
   kept: the first drew the sparkles in the shape of a person facing the
   camera (`figure_rejected.jpg`), which could never line up with an
   isometric character facing eight ways; the second a glass tube with a hard
   rim (`tube_rejected.jpg`). The prompt that worked says what it is **not**:
   no outline, no rim, no tube, no human shape.
2. **Each next frame from the one before it**, so the animation really moves:
   the sparkles drift upward, glints dim and new ones flare. The first link
   was `edit-image` on frame 00.
3. **Anchored to frame 00 as a style reference** (`compose-images`: the first
   image the previous frame, the second frame 00). A plain chain drifted
   within two links -- each generation copies a little of the small, soft
   input it is handed, and `frame_02_rejected_soft.jpg` is where it went
   blurry with half the glints. With the anchor, every frame kept the look.
4. **The fade the same way**: "a third of the sparkles gone", "a third of
   those left", "the last dozen points".

**Pass frames small.** A frame goes to the toolkit as bare base64 typed into
the call, so each was sent at 128x256 (5 KB); the anchor at 192x384 (13 KB).
Gemini still returns full size. **And normalise before chaining**: frame 01
came back 848x1264 rather than 720x1456 with the column off centre, and
feeding that forward compounds it.

**FlowDot's image storage** was full again (about a hundred images); 24 of the
oldest were deleted, with the author's go-ahead, to make room.

`python tools/gen_beam.py TrekShuttle/42` bakes the raws, every run:

- **normalised**: each frame found by its glow and put in one place at one
  size (the glow's core 0.84 of the frame tall, centred). A faint frame, too
  dim to be found by, inherits the placement of the last frame that was not
  and was the same size;
- **black to transparent**: alpha is the brightest channel and the colour is
  divided by it, lifted a little (`LIFT`) so it still reads over pale ground.
  Drawn on black, not magenta, because a glow keyed off magenta leaves a
  purple fringe everywhere it is soft, and here everything is soft;
- **edges faded**, so nothing a crop cut through shows as a line;
- **`design/art/beam/beam_sheet.png`**: every frame over dark, grass and pale
  ground, and both sequences in the order the game plays them.

---

## 3. How it works

| What | Where |
|---|---|
| Which moves are beams; timings, size, opacity | `TREK_Config.lua`, `C.BeamFxKinds`, `C.BeamFx` |
| Which frame shows when; the texture names | `shared/TREK/TREK_Beam.lua` (`B.frameAt`) |
| Announcing a departure; relaying an arrival | `server/TREK/TREK_BeamServer.lua` |
| The call from the `move` handler | `TREK_Server.lua`, just before `moveGranted` |
| Watching for the local player's arrival | `client/TREK/TREK_BeamFX.lua` (`FX.watchFrom`), called from `TREK_Core`'s `moveGranted` |
| Drawing | `TREK_BeamFX.lua`, a 1x1 overlay |
| Tests | `tests/test_multiplayer.py`: `beam()`, `beam_multiplayer()` |

- **A departure is the server's to announce.** Every beam is a `move` the
  server grants, and its handler runs while the character is still where they
  are leaving from, so `BS.departing` sends `beamFx` (phase `out`) to every
  client from there. No feature needed a hook.
- **An arrival is the moving client's to see.** The client moves its own
  character, so it notes where its player stood when the beam was granted
  (before `onGranted`, because a recover moves them inside it) and the first
  tick they are more than `C.BeamFx.jump` tiles away, or on another storey,
  is the arrival. It shows the column at once and sends `beamedIn`; the
  server relays it to everybody. One watcher covers the pad, a beam down, the
  Adirondack and a raid.
- **The server relays only arrivals it sent somebody on**: one per granted
  beam, within `arrivalWindowMs`. A client cannot make sparkles on demand.
- **Following.** A column follows its character -- one of this machine's own
  players, or anybody the engine knows by that online id. A leaving column
  stops following, and starts to fade, the moment its character is seen to
  go: a jump, a change of storey, or vanishing from this machine. If that is
  never seen it fades at `outMaxMs`. It always shimmers at least one full
  cycle, because straight from the build into the fade is a flash.
- **Drawn on a 1x1 overlay** in screen space, the phaser's rule: an overlay
  the size of the screen takes the world's right-click and aiming away.
- **Where:** the glow's foot at the character's feet, its core
  `C.BeamFx.height` storeys tall, measured each frame from `isoToScreenY` a
  storey apart, so it scales with the zoom.

---

## 4. Why the character does not fade

The obvious effect -- the figure fading out under the sparkles -- is not
reachable from Lua. The engine sets every visible character's alpha each
frame: `IsoPlayer.updateLOS` (`setAlphaAndTarget` at bci 276-426) and, on a
client, `IsoPlayer.render` (`setTargetAlpha(0 or 1)` at bci 141/166, by
whether they can be seen). An alpha set from Lua is overwritten before the
character is drawn, in every process, and fighting it frame by frame would
flicker in multiplayer. So the column covers them at its peak, and when they
go they are gone from under it.

---

## 5. Testing

```sh
TREK_ONLY=beam,beam_multiplayer python tests/test_multiplayer.py
python tests/test_assets.py          # the seven frames exist (named whole in TREK_Beam.lua)
```

**`beam()`**, single player: every `C.BeamFxKinds` entry is a move the
server's `MOVES` grants, and the walks are not beams; the timeline (built
from nothing leaving, full strength arriving, shimmer only frames 0-3, fade
4-5-6 and end, the fade starting the moment they go, at least one shimmer);
a real beam up from the ground -- a column under the player, drawn centred on
them with its foot at their feet, at 1:2, the overlay under no point of the
screen, then frozen where they stood once they went, the moment they went
fixed and the column fading a tenth of a second later, a second column on the
pad, the watcher cleared, and nothing left afterwards; a **recover** (home to
the pad after a landing with no room), the one beam that moves the player
inside `onGranted`; and a forged `beamedIn` relayed to nobody.

**`beam_multiplayer()`**: bob sees alice's column go up where she stood and
sees her go; alice sees her own; bob gets her arrival where her client said
she landed; alice's machine is asked to show her arrival exactly twice (her
watcher, then the relay) and keeps the same column; and bob's forged arrival
reaches nobody.

**Fourteen mutations, one pass at a time, all caught** -- three only after
their tests were fixed, and each of the three is worth knowing:

- *The column goes on looking for them after they went.* The column stayed in
  the right place, which was all the test asked; it was the fade that kept
  being put off, re-detected every tick. The test now asks that the moment
  they went stays fixed.
- *The watcher set after `onGranted`.* Harmless for every beam but a recover,
  which the test had never done.
- *No guard against the relay restarting her own arrival.* In the harness
  her report, the server's relay and the restart all land inside one tick, at
  one timestamp, so neither the time nor a look after the tick can see it;
  only wrapping `FX.start` and comparing the tables its two calls returned
  (in Lua, with `rawequal`) can.

The first cut of the tests also looked 3.2 s after the beam, when both
columns had long finished, so every check on them was skipped behind an
`if ... is not None` -- *a scenario that never reaches the condition is not a
test of it*. They step tick by tick and look the moment the player lands.

The harness records beam draws apart from the phaser's sparks
(`SIM.beamDraws`): lumped together, no test could tell one from the other.

---

## 6. Not yet seen

Played 2026-09-29 and passed: the look, the timing against the real move,
and arriving aboard. Left:

1. **Two players**: the other player's columns, which only a second person
   can confirm.

## 7. Open

- **No sound.** A transporter hum would go with it; `tools/gen_phaser.py`'s
  synthesis is the way to make one.
- **The character does not fade** (section 4).
