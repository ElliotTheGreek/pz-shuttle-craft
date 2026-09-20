"""Generates the replicator: its materialisation sound, and its alcove.

    python tools/gen_replicator.py TrekShuttle/42

Two assets, both procedural and both deterministic, plus the render the model
was judged on -- which goes in design/art/replicator/ on every run, so the
generator and the vet are the same command and the picture cannot go stale.

**The model is a wall alcove, not a box on the deck.** The berth at 0,5 is a
steel counter, and a floor-standing unit on the same square would be drawn
through it. This is authored from 0.86 up instead, so it hangs above the
bench the way every replicator in the show does: counter below, lit recess
above. Y is up, as it is for every world model here, and one unit is one tile.

The sound is synthesized from the standard library -- the
sparkle runs off its own seeded generator rather than `random`, so re-running
this writes a byte-identical file and a regenerated asset is never a silent
diff. It is not copied franchise audio: it is three oscillator banks and an
envelope, built to the same recipe as tools/gen_medical.py's three.

Played with playSoundLocal, like the medical set's: it belongs to whoever is
standing at the machine, it does not travel, and -- the half that matters --
it does not put a noise on the map for the dead to walk towards. A galley
appliance that called a horde would be a strange thing to build into a ship.

The shape of it is the shape of the effect: a field builds (a rising hum), the
pattern resolves (a shimmer of high partials beating against each other), and
the thing is there (a short bell). Deliberately under a second -- it plays on
every item, and a long sound is charming once and tiresome at the tenth.
"""
import math
import os
import struct
import subprocess
import sys
import wave

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pngwrite import Image, draw_text
from meshbuild import MeshBuilder

RATE = 44100


class Noise:
    """A tiny LCG, so the sparkle is the same sparkle on every machine."""

    def __init__(self, seed=20260921):
        self.state = seed

    def next(self):
        self.state = (self.state * 1103515245 + 12345) & 0x7FFFFFFF
        return self.state / 0x3FFFFFFF - 1.0


def write(path, samples, peak=25000):
    frames = b"".join(
        struct.pack("<h", int(max(-1.0, min(1.0, s)) * peak)) for s in samples)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(RATE)
        out.writeframes(frames)
    print(f"  {os.path.basename(path)}  {len(samples) / RATE:.2f}s")


def materialise(duration=0.78):
    """The field, the shimmer and the bell, in that order and overlapping.

    The three layers are what keeps it from reading as a UI beep:

      * the **field** is a low pair of detuned oscillators that rise about a
        fifth over the first half and then hold -- the machine committing;
      * the **shimmer** is five high partials, each amplitude-modulated at its
        own rate, so they beat against each other instead of forming a chord.
        That interference *is* the transporter-ish character; a single high
        sine sounds like a microwave finishing;
      * the **bell** is one short struck partial at the end, which is the only
        part a player consciously hears: it says the thing is in the tray.
    """
    noise = Noise()
    out = []
    n = int(RATE * duration)
    field_a = field_b = 0.0
    shimmer_phase = [0.0] * 5
    bell_phase = 0.0
    bell_at = duration * 0.62

    # Five partials, none of them a whole-number multiple of another: whole
    # multiples would lock into a chord and stop shimmering.
    partials = ((1840.0, 6.1), (2270.0, 7.7), (2910.0, 4.3),
                (3480.0, 9.2), (4130.0, 5.6))

    for i in range(n):
        t = i / RATE
        progress = t / duration

        # --- the field ---------------------------------------------------
        rise = min(1.0, t / (duration * 0.30))
        fall = min(1.0, (1.0 - progress) / 0.30)
        field_env = rise * fall
        lift = 1.0 + 0.48 * min(1.0, progress / 0.5)
        field_a += 2 * math.pi * 180.0 * lift / RATE
        field_b += 2 * math.pi * 181.7 * lift / RATE       # detuned: a slow beat
        field = (0.22 * math.sin(field_a) + 0.20 * math.sin(field_b)) * field_env

        # --- the shimmer -------------------------------------------------
        shimmer = 0.0
        shimmer_env = (min(1.0, t / 0.06) * math.exp(-2.0 * progress)
                       * (0.55 + 0.45 * math.sin(math.pi * progress)))
        for k, (freq, rate) in enumerate(partials):
            shimmer_phase[k] += 2 * math.pi * freq / RATE
            am = 0.5 + 0.5 * math.sin(2 * math.pi * rate * t + k)
            shimmer += math.sin(shimmer_phase[k]) * am
        shimmer *= 0.075 * shimmer_env
        # a whisper of noise under it, so the partials are not naked sines
        shimmer += 0.018 * noise.next() * shimmer_env

        # --- the bell ------------------------------------------------------
        bell = 0.0
        if t >= bell_at:
            bt = t - bell_at
            bell_phase += 2 * math.pi * 1240.0 / RATE
            bell = (0.30 * math.sin(bell_phase)
                    + 0.10 * math.sin(bell_phase * 2.01)) * math.exp(-7.5 * bt)

        out.append(field + shimmer + bell)
    return out


# ---------------------------------------------------------------------------
# The alcove
# ---------------------------------------------------------------------------
TEX_W = TEX_H = 128
UP_AXIS = "y"

# Against the port bulkhead, opening east into the cabin. `place` maps
# (east, north, height), so a smaller east value is further into the wall.
# Sized down after the first look in game, where it was the tallest thing in
# the galley and read as a monolith floating over the bench -- "out of place",
# and fairly. Two thirds of the height and a narrower box puts it in the row
# with the microwave and the oven instead of above them all.
BACK, FRONT = -0.44, 0.10           # east: the wall, and the lip of the frame
SIDE = 0.34                         # north and south half-width
Y0, Y1 = 0.86, 1.46                 # it starts above the counter, not on it
# Shallow on purpose. The first cut put the emitter back at -0.24 and the
# recess rendered as a hole straight through the unit: the lit panel was a
# sliver and the cavity walls ate the rest. A replicator is a lit niche, not
# a cupboard, so the panel sits just inside the lip.
CAVITY_BACK = 0.02                  # where the emitter panel sits
OPEN_SIDE, OPEN_Y0, OPEN_Y1 = 0.24, 0.98, 1.32

CASE      = (92, 98, 112, 255)
CASE_LITE = (126, 132, 148, 255)
CASE_DEEP = (52, 56, 66, 255)
BLACK     = (14, 15, 19, 255)
RECESS    = (48, 54, 64, 255)
GLOW      = (150, 222, 255, 255)
GLOW_DEEP = (36, 96, 150, 255)
AMBER     = (238, 154, 62, 255)
SAND      = (222, 186, 122, 255)
LILAC     = (162, 146, 216, 255)
SKY       = (118, 176, 236, 255)
BAR = [AMBER, SAND, LILAC, SKY]

REGIONS = {
    "frame":   (0, 0, 64, 64),       # the LCARS surround
    "emitter": (66, 0, 128, 64),     # the lit back panel
    "case":    (0, 66, 64, 128),     # the louvred flanks
    "recess":  (66, 66, 128, 96),    # the inside of the cavity
    # The top has its own panel, and that is not fussiness: the game's camera
    # looks down at everything, so the lid is half of what a player sees of
    # this. Wearing the flank's louvres it rendered as the lid of a crate.
    "top":     (66, 98, 128, 128),
}


def paint_frame(img):
    """The surround: a Starfleet panel with a spine and a few readouts."""
    x0, y0, x1, y1 = REGIONS["frame"]
    img.rect(x0, y0, x1, y1, CASE)
    img.rect(x0 + 1, y0 + 1, x1 - 1, y0 + 3, CASE_LITE)
    img.rect(x0 + 2, y0 + 6, x0 + 8, y1 - 6, AMBER)
    for i in range(4):
        yy = y0 + 8 + i * 13
        img.rect(x0 + 10, yy, x0 + 10 + 7 + (i % 3) * 5, yy + 8, BAR[i % len(BAR)])
    for r in range(5):
        yy = y0 + 10 + r * 10
        run = x0 + 34
        for i in range(3):
            wd = 4 + ((r * 3 + i * 4) % 8)
            if run + wd > x1 - 3:
                break
            img.rect(run, yy, run + wd, yy + 4, BAR[(r + i) % len(BAR)])
            run += wd + 2
    img.rect(x0, y1 - 3, x1, y1, CASE_DEEP)


def paint_emitter(img):
    """The back of the recess: where the thing appears.

    A gradient rather than a flat colour, because at this size a flat bright
    rectangle reads as a hole in the model rather than as a lit surface.
    """
    x0, y0, x1, y1 = REGIONS["emitter"]
    img.rect(x0, y0, x1, y1, BLACK)
    h = y1 - y0
    for i in range(h - 6):
        k = i / max(1, h - 7)
        # brightest across the middle, falling off up and down
        f = 1.0 - abs(k - 0.5) * 1.7
        f = max(0.0, min(1.0, f))
        c = tuple(int(GLOW_DEEP[j] + (GLOW[j] - GLOW_DEEP[j]) * f) for j in range(3))
        img.rect(x0 + 3, y0 + 3 + i, x1 - 3, y0 + 4 + i, c + (255,))
    # the containment grid, so it is a field and not a lamp
    for i in range(y0 + 6, y1 - 4, 7):
        img.rect(x0 + 4, i, x1 - 4, i + 1, GLOW_DEEP)
    for i in range(x0 + 6, x1 - 4, 8):
        img.rect(i, y0 + 5, i + 1, y1 - 5, GLOW_DEEP)
    # No lettering. At the size this is drawn in game a word is four grey
    # pixels, and the icons that came before it taught this the hard way.


def paint_case(img):
    x0, y0, x1, y1 = REGIONS["case"]
    img.rect(x0, y0, x1, y1, CASE)
    img.rect(x0, y0, x1, y0 + 2, CASE_LITE)
    img.rect(x0, y1 - 3, x1, y1, CASE_DEEP)
    for i in range(x0 + 6, x1 - 4, 11):
        img.rect(i, y0 + 10, i + 5, y1 - 10, CASE_DEEP)

    x0, y0, x1, y1 = REGIONS["recess"]
    img.rect(x0, y0, x1, y1, RECESS)
    # a lit lip along the top of the recess, so the cavity is a niche with a
    # light in it rather than a black rectangle
    img.rect(x0 + 2, y0 + 2, x1 - 2, y0 + 5, GLOW_DEEP)

    x0, y0, x1, y1 = REGIONS["top"]
    img.rect(x0, y0, x1, y1, CASE)
    img.rect(x0 + 3, y0 + 3, x1 - 3, y1 - 3, CASE_LITE)
    img.rect(x0 + 6, y0 + 6, x1 - 6, y1 - 6, CASE)
    img.rect(x0 + 9, y0 + 9, x0 + 26, y0 + 12, SKY)
    img.rect(x0 + 9, y0 + 15, x0 + 18, y0 + 18, AMBER)


def build_atlas(path):
    img = Image(TEX_W, TEX_H, CASE_DEEP)
    paint_frame(img)
    paint_emitter(img)
    paint_case(img)
    img.save(path)


def build_mesh(path):
    m = MeshBuilder(TEX_W, TEX_H, up_axis=UP_AXIS)
    R, P = REGIONS, None
    P = m.place

    # --- the shell ------------------------------------------------------
    # North and south flanks, the top, the underside and the back against the
    # bulkhead. The underside matters: this hangs over a counter and is looked
    # at from below more than a floor-standing unit ever is.
    m.quad(P(BACK, -SIDE, Y0), P(FRONT, -SIDE, Y0),
           P(FRONT, -SIDE, Y1), P(BACK, -SIDE, Y1), R["case"], P(0, -1, 0))
    m.quad(P(FRONT, SIDE, Y0), P(BACK, SIDE, Y0),
           P(BACK, SIDE, Y1), P(FRONT, SIDE, Y1), R["case"], P(0, 1, 0))
    m.quad(P(BACK, -SIDE, Y1), P(FRONT, -SIDE, Y1),
           P(FRONT, SIDE, Y1), P(BACK, SIDE, Y1), R["top"], P(0, 0, 1))
    m.quad(P(BACK, SIDE, Y0), P(FRONT, SIDE, Y0),
           P(FRONT, -SIDE, Y0), P(BACK, -SIDE, Y0), R["top"], P(0, 0, -1))
    m.quad(P(BACK, SIDE, Y0), P(BACK, -SIDE, Y0),
           P(BACK, -SIDE, Y1), P(BACK, SIDE, Y1), R["case"], P(-1, 0, 0))

    # --- the front, as a frame around the opening -----------------------
    # Four strips rather than one face: the hole in the middle is what makes
    # this an alcove rather than a cupboard door.
    for (b0, b1, y0, y1) in (
            (-SIDE, SIDE, OPEN_Y1, Y1),            # above
            (-SIDE, SIDE, Y0, OPEN_Y0),            # below
            (-SIDE, -OPEN_SIDE, OPEN_Y0, OPEN_Y1),  # south post
            (OPEN_SIDE, SIDE, OPEN_Y0, OPEN_Y1)):   # north post
        m.quad(P(FRONT, b0, y0), P(FRONT, b1, y0),
               P(FRONT, b1, y1), P(FRONT, b0, y1), R["frame"], P(1, 0, 0))

    # --- the cavity ------------------------------------------------------
    m.quad(P(CAVITY_BACK, -OPEN_SIDE, OPEN_Y0), P(FRONT, -OPEN_SIDE, OPEN_Y0),
           P(FRONT, -OPEN_SIDE, OPEN_Y1), P(CAVITY_BACK, -OPEN_SIDE, OPEN_Y1),
           R["recess"], P(0, 1, 0))
    m.quad(P(FRONT, OPEN_SIDE, OPEN_Y0), P(CAVITY_BACK, OPEN_SIDE, OPEN_Y0),
           P(CAVITY_BACK, OPEN_SIDE, OPEN_Y1), P(FRONT, OPEN_SIDE, OPEN_Y1),
           R["recess"], P(0, -1, 0))
    m.quad(P(CAVITY_BACK, OPEN_SIDE, OPEN_Y0), P(FRONT, OPEN_SIDE, OPEN_Y0),
           P(FRONT, -OPEN_SIDE, OPEN_Y0), P(CAVITY_BACK, -OPEN_SIDE, OPEN_Y0),
           R["recess"], P(0, 0, 1))
    m.quad(P(CAVITY_BACK, -OPEN_SIDE, OPEN_Y1), P(FRONT, -OPEN_SIDE, OPEN_Y1),
           P(FRONT, OPEN_SIDE, OPEN_Y1), P(CAVITY_BACK, OPEN_SIDE, OPEN_Y1),
           R["recess"], P(0, 0, -1))
    # the emitter, looking out of the recess
    m.quad(P(CAVITY_BACK, -OPEN_SIDE, OPEN_Y0), P(CAVITY_BACK, OPEN_SIDE, OPEN_Y0),
           P(CAVITY_BACK, OPEN_SIDE, OPEN_Y1), P(CAVITY_BACK, -OPEN_SIDE, OPEN_Y1),
           R["emitter"], P(1, 0, 0))

    return m.emit(path, "TREKReplicator", "TREK_Replicator.png")


def preview(root, mesh, texture):
    """Renders the alcove into design/art/replicator/, front and three-quarter.

    Four separate faults in the hull were invisible in the source and obvious
    in one frame of this, so it runs on every generation rather than when
    somebody remembers.
    """
    out = os.path.join("design", "art", "replicator")
    os.makedirs(out, exist_ok=True)
    tool = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "preview_model.py")
    # 270 looks straight into the alcove and 225 is the three-quarter the
    # game's camera actually shows. The first pass rendered 0 and 40, which
    # are both the back of the unit: two pictures of a louvred box.
    for yaw, name in ((270, "front"), (225, "quarter")):
        target = os.path.join(out, f"preview_replicator_{name}.png")
        subprocess.run([sys.executable, tool, mesh, texture, target, str(yaw)],
                       check=False)
    return out


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else "TrekShuttle/42"
    sound = os.path.join(root, "media", "sound")
    write(os.path.join(sound, "TREK_Replicate.wav"), materialise())

    texture = os.path.join(root, "media", "textures", "TREK_Replicator.png")
    mesh = os.path.join(root, "media", "models_X", "TREK_Replicator.x")
    os.makedirs(os.path.dirname(texture), exist_ok=True)
    os.makedirs(os.path.dirname(mesh), exist_ok=True)
    build_atlas(texture)
    nv, nf = build_mesh(mesh)
    print(f"  TREK_Replicator.x  {nv} verts, {nf} tris")
    print(f"  renders in {preview(root, mesh, texture)}")
    print("replicator sound and alcove written")
