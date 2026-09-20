"""Generates the replicator: the machine itself, and its materialisation sound.

    python tools/gen_replicator.py TrekShuttle/42

Two assets, both procedural and both deterministic, plus the renders the model
was judged on -- which go in design/art/replicator/ on every run, so the
generator and the vet are the same command and the picture cannot go stale.

**It is a whole machine standing on the deck, and it owns its square.** For
two revisions it was a wall alcove hanging over a galley counter, and that was
wrong twice over: the counter was doing the work the replicator should have
been doing, and a model drawn above its own square cannot be right-clicked at
all (DEV_GUIDE.md, "A right-click lands on the floor, not on the picture").
There is no counter under it now. A kick plinth, a body with a lit niche at
chest height, a shelf under the niche and a capped top with a readout.

Y is up, as for every world model here, and one unit is one tile.

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
# The machine
# ---------------------------------------------------------------------------
TEX_W, TEX_H = 128, 192
UP_AXIS = "y"

# `place` maps (east, north, height). It stands against the port bulkhead, so
# the smaller east value is its back, into the wall, and the face looks east
# into the cabin -- which is also the way the game's camera shows it.
BACK, FRONT = -0.46, 0.22           # against the wall, and its face
SIDE = 0.40                         # north and south half-width
INSET = 0.06                        # how far the plinth is tucked under
TOP = 1.62                          # a shade under a fridge

PLINTH = 0.16                       # the kick at the bottom
CAP = 1.46                          # where the capped top begins

# The niche, at chest height, with a shelf proud of the face under it.
OPEN_SIDE = 0.27
OPEN_Y0, OPEN_Y1 = 0.62, 1.18
CAVITY_BACK = 0.02                  # shallow: a lit niche, not a cupboard
SHELF = 0.30                        # how far the lip stands out past the face

CASE      = (96, 102, 116, 255)
CASE_LITE = (132, 138, 154, 255)
CASE_DEEP = (56, 60, 70, 255)
PLINTH_C  = (44, 47, 56, 255)
BLACK     = (16, 17, 22, 255)
RECESS    = (52, 58, 68, 255)
GLOW      = (158, 226, 255, 255)
GLOW_DEEP = (38, 100, 156, 255)
AMBER     = (238, 154, 62, 255)
SAND      = (222, 186, 122, 255)
LILAC     = (162, 146, 216, 255)
SKY       = (118, 176, 236, 255)
BAR = [AMBER, SAND, LILAC, SKY]

REGIONS = {
    "frame":   (0, 0, 64, 64),        # the face: LCARS around the niche
    "emitter": (64, 0, 128, 64),      # the lit back of the niche
    "flank":   (0, 64, 64, 128),      # north and south sides
    "recess":  (64, 64, 128, 128),    # the inside of the niche
    "top":     (0, 128, 64, 192),     # the cap, and the shelf
    "plinth":  (64, 128, 128, 192),   # the kick, the back and the undersides
}


def panel(img, region, base=CASE):
    """A plain brushed panel, lit along the top and seamed at the bottom."""
    x0, y0, x1, y1 = region
    img.rect(x0, y0, x1, y1, base)
    img.rect(x0, y0, x1, y0 + 2, CASE_LITE)
    img.rect(x0, y1 - 3, x1, y1, CASE_DEEP)
    return x0, y0, x1, y1


def paint_frame(img):
    """The face. At one tile this is a colour and a shape, not detail."""
    x0, y0, x1, y1 = panel(img, REGIONS["frame"])
    img.rect(x0 + 3, y0 + 5, x0 + 10, y1 - 5, AMBER)
    for i in range(5):
        yy = y0 + 7 + i * 11
        img.rect(x0 + 12, yy, x0 + 12 + 6 + (i % 3) * 5, yy + 7, BAR[i % len(BAR)])
    for r in range(6):
        yy = y0 + 8 + r * 9
        run = x0 + 36
        for i in range(3):
            wd = 4 + ((r * 3 + i * 5) % 9)
            if run + wd > x1 - 4:
                break
            img.rect(run, yy, run + wd, yy + 4, BAR[(r + i) % len(BAR)])
            run += wd + 2


def paint_emitter(img):
    """Where the thing appears: a field, brightest across the middle.

    A gradient rather than a flat colour. At this size a flat bright rectangle
    reads as a hole in the model rather than as a lit surface.
    """
    x0, y0, x1, y1 = REGIONS["emitter"]
    img.rect(x0, y0, x1, y1, BLACK)
    h = y1 - y0
    for i in range(h - 6):
        k = i / max(1, h - 7)
        f = max(0.0, min(1.0, 1.0 - abs(k - 0.5) * 1.7))
        c = tuple(int(GLOW_DEEP[j] + (GLOW[j] - GLOW_DEEP[j]) * f) for j in range(3))
        img.rect(x0 + 3, y0 + 3 + i, x1 - 3, y0 + 4 + i, c + (255,))
    for i in range(y0 + 6, y1 - 4, 7):
        img.rect(x0 + 4, i, x1 - 4, i + 1, GLOW_DEEP)
    for i in range(x0 + 6, x1 - 4, 8):
        img.rect(i, y0 + 5, i + 1, y1 - 5, GLOW_DEEP)


def paint_flank(img):
    """The sides, and the south one is half of what the camera ever shows.

    Panelled rather than louvred: the louvres on the first model are what made
    it read as a wheelie bin from three-quarters on.
    """
    x0, y0, x1, y1 = panel(img, REGIONS["flank"])
    img.rect(x0 + 5, y0 + 8, x1 - 5, y1 - 14, CASE_DEEP)
    img.rect(x0 + 7, y0 + 10, x1 - 7, y1 - 16, CASE)
    img.rect(x0 + 10, y1 - 11, x0 + 26, y1 - 8, SKY)


def paint_rest(img):
    x0, y0, x1, y1 = REGIONS["recess"]
    img.rect(x0, y0, x1, y1, RECESS)
    img.rect(x0 + 2, y0 + 2, x1 - 2, y0 + 6, GLOW_DEEP)

    x0, y0, x1, y1 = panel(img, REGIONS["top"])
    img.rect(x0 + 4, y0 + 4, x1 - 4, y1 - 4, CASE_LITE)
    img.rect(x0 + 7, y0 + 7, x1 - 7, y1 - 7, CASE)
    img.rect(x0 + 11, y0 + 11, x0 + 30, y0 + 15, SKY)
    img.rect(x0 + 11, y0 + 19, x0 + 22, y0 + 23, AMBER)

    x0, y0, x1, y1 = REGIONS["plinth"]
    img.rect(x0, y0, x1, y1, PLINTH_C)
    img.rect(x0, y0, x1, y0 + 2, CASE_DEEP)


def build_atlas(path):
    img = Image(TEX_W, TEX_H, CASE_DEEP)
    paint_frame(img)
    paint_emitter(img)
    paint_flank(img)
    paint_rest(img)
    img.save(path)


def build_mesh(path):
    m = MeshBuilder(TEX_W, TEX_H, up_axis=UP_AXIS)
    R = REGIONS
    P = m.place

    def east_face(y0, y1, b0, b1, east, region):
        m.quad(P(east, b0, y0), P(east, b1, y0),
               P(east, b1, y1), P(east, b0, y1), region, P(1, 0, 0))

    # --- the plinth ------------------------------------------------------
    # Tucked in on every side, so the body overhangs it and the machine
    # stands on the deck rather than being a box set down on it.
    pb, pf, ps = BACK + INSET, FRONT - INSET, SIDE - INSET
    m.quad(P(pb, -ps, 0), P(pf, -ps, 0), P(pf, -ps, PLINTH), P(pb, -ps, PLINTH),
           R["plinth"], P(0, -1, 0))
    m.quad(P(pf, ps, 0), P(pb, ps, 0), P(pb, ps, PLINTH), P(pf, ps, PLINTH),
           R["plinth"], P(0, 1, 0))
    east_face(0, PLINTH, -ps, ps, pf, R["plinth"])

    # --- the body --------------------------------------------------------
    m.quad(P(BACK, -SIDE, PLINTH), P(FRONT, -SIDE, PLINTH),
           P(FRONT, -SIDE, TOP), P(BACK, -SIDE, TOP), R["flank"], P(0, -1, 0))
    m.quad(P(FRONT, SIDE, PLINTH), P(BACK, SIDE, PLINTH),
           P(BACK, SIDE, TOP), P(FRONT, SIDE, TOP), R["flank"], P(0, 1, 0))
    m.quad(P(BACK, SIDE, PLINTH), P(BACK, -SIDE, PLINTH),
           P(BACK, -SIDE, TOP), P(BACK, SIDE, TOP), R["plinth"], P(-1, 0, 0))
    m.quad(P(BACK, SIDE, PLINTH), P(FRONT, SIDE, PLINTH),
           P(FRONT, -SIDE, PLINTH), P(BACK, -SIDE, PLINTH),
           R["plinth"], P(0, 0, -1))
    m.quad(P(BACK, -SIDE, TOP), P(FRONT, -SIDE, TOP),
           P(FRONT, SIDE, TOP), P(BACK, SIDE, TOP), R["top"], P(0, 0, 1))
    east_face(CAP, TOP, -SIDE, SIDE, FRONT, R["top"])

    # --- the face, as a frame around the niche ---------------------------
    for (b0, b1, y0, y1) in (
            (-SIDE, SIDE, OPEN_Y1, CAP),
            (-SIDE, SIDE, PLINTH, OPEN_Y0),
            (-SIDE, -OPEN_SIDE, OPEN_Y0, OPEN_Y1),
            (OPEN_SIDE, SIDE, OPEN_Y0, OPEN_Y1)):
        east_face(y0, y1, b0, b1, FRONT, R["frame"])

    # --- the niche -------------------------------------------------------
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
    m.quad(P(CAVITY_BACK, -OPEN_SIDE, OPEN_Y0), P(CAVITY_BACK, OPEN_SIDE, OPEN_Y0),
           P(CAVITY_BACK, OPEN_SIDE, OPEN_Y1), P(CAVITY_BACK, -OPEN_SIDE, OPEN_Y1),
           R["emitter"], P(1, 0, 0))

    # --- the shelf under the niche ---------------------------------------
    # Where a cup would stand. It is also what stops the face reading as one
    # flat rectangle from across the room.
    sh, lip = OPEN_Y0, 0.05
    m.quad(P(FRONT, -OPEN_SIDE, sh), P(SHELF, -OPEN_SIDE, sh),
           P(SHELF, OPEN_SIDE, sh), P(FRONT, OPEN_SIDE, sh), R["top"], P(0, 0, 1))
    m.quad(P(SHELF, OPEN_SIDE, sh - lip), P(SHELF, -OPEN_SIDE, sh - lip),
           P(SHELF, -OPEN_SIDE, sh), P(SHELF, OPEN_SIDE, sh),
           R["frame"], P(1, 0, 0))
    m.quad(P(FRONT, OPEN_SIDE, sh - lip), P(SHELF, OPEN_SIDE, sh - lip),
           P(SHELF, OPEN_SIDE, sh), P(FRONT, OPEN_SIDE, sh),
           R["plinth"], P(0, 1, 0))
    m.quad(P(SHELF, -OPEN_SIDE, sh - lip), P(FRONT, -OPEN_SIDE, sh - lip),
           P(FRONT, -OPEN_SIDE, sh), P(SHELF, -OPEN_SIDE, sh),
           R["plinth"], P(0, -1, 0))
    m.quad(P(SHELF, OPEN_SIDE, sh - lip), P(FRONT, OPEN_SIDE, sh - lip),
           P(FRONT, -OPEN_SIDE, sh - lip), P(SHELF, -OPEN_SIDE, sh - lip),
           R["plinth"], P(0, 0, -1))

    return m.emit(path, "TREKReplicator", "TREK_Replicator.png")


def preview(root, mesh, texture):
    """Renders it into design/art/replicator/ on every run.

    270 looks straight at the face and 225 is the three-quarter the game's
    camera actually shows. The first pass rendered 0 and 40, which are both
    the back of the unit: two careful pictures of a louvred box.
    """
    out = os.path.join("design", "art", "replicator")
    os.makedirs(out, exist_ok=True)
    tool = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "preview_model.py")
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
    print("replicator sound and model written")
