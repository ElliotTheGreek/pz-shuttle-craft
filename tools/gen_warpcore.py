"""Generates the dilithium chamber: a small warp core for the shuttle's cabin.

    python tools/gen_warpcore.py TrekShuttle/42

**Why it is a model and not a cupboard.** The crystals lived in a vanilla Tool
Cabinet for one revision, which worked and looked like a tool cabinet. A
container in this engine comes from a *tile sprite's* properties, so a custom
model cannot be one -- and standing a model over a cabinet to borrow its
container is the exact arrangement the replicator was rebuilt to get rid of
(DEV_GUIDE.md, "A fixture that leans on another fixture is not a fixture
yet"). So the core is the whole thing, and what it holds is ship state:
TREK_Power keeps the count, the menu on its square loads and takes crystals,
and the tricorder reads it like any other cache.

Authored from the deck up, Y up, one unit to a tile, and **slim**: it stands
in the port passage where the crew walk past it, so it is a column rather than
a wardrobe.

The shape is the one thing on this ship a player will recognise on sight:

  * a dark base, wider than the body, so it sits on the deck;
  * a lower housing with the ship's LCARS colours on it;
  * the **core column** -- an octagonal prism of plasma, banded, bright in the
    middle and deep blue at the edges. The banding is what says "moving" in a
    still image, which is all the game's camera ever gives it;
  * the **articulation collar** at chest height, wider than the column, with a
    lit window in it. That window is violet, not blue, because it is the
    crystal: the one part of the machine the player has to go out and find;
  * an upper housing and a capped top.

Deterministic: no randomness anywhere, so re-running it writes a byte-identical
file and a regenerated asset is never a silent diff.
"""
import math
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pngwrite import Image
from meshbuild import MeshBuilder

TEX_W, TEX_H = 128, 192
UP_AXIS = "y"

# --- the dimensions, one dial ---------------------------------------------
# It shares a passage with the crew, so it is authored narrow and sized from
# the replicator's own lesson: a fixture is judged standing beside the things
# it shares a bulkhead with, not in a render.
SCALE = 1.0

R_BASE   = 0.30 * SCALE            # the plinth's half-width
R_BODY   = 0.24 * SCALE            # the housings
R_CORE   = 0.19 * SCALE            # the plasma column, tucked inside them
R_COLLAR = 0.27 * SCALE            # the articulation collar, proud of the rest

H_BASE   = 0.10 * SCALE
H_LOWER  = 0.32 * SCALE            # where the column starts
H_COL0   = 0.58 * SCALE            # the collar, at chest height
H_COL1   = 0.70 * SCALE
H_UPPER  = 1.12 * SCALE            # where the column ends
H_TOP    = 1.30 * SCALE
# The first render was a stack of drums: the housings were as tall as the
# plasma and the eye read five equal bands. The column is the machine, so it
# carries two thirds of the height and the housings are collars on it.

# Eight sides. Enough to read as round at one tile, few enough that the whole
# thing is still under a hundred triangles.
SIDES = 8

CASE      = (98, 104, 118, 255)
CASE_LITE = (136, 142, 158, 255)
CASE_DEEP = (54, 58, 68, 255)
BASE_C    = (38, 41, 49, 255)
BLACK     = (14, 15, 20, 255)
PLASMA    = (214, 240, 255, 255)
PLASMA_MID= (96, 178, 240, 255)
PLASMA_LOW= (22, 62, 122, 255)
CRYSTAL   = (196, 150, 246, 255)
CRYSTAL_HI= (238, 224, 255, 255)
CRYSTAL_LO= (86, 54, 138, 255)
AMBER     = (238, 154, 62, 255)
LILAC     = (162, 146, 216, 255)
SKY       = (118, 176, 236, 255)
BAR = [AMBER, LILAC, SKY]

REGIONS = {
    "case":    (0, 0, 64, 64),        # the housings
    "plasma":  (64, 0, 128, 64),      # the column
    "collar":  (0, 64, 64, 128),      # the articulation collar and its window
    "top":     (64, 64, 128, 128),    # the cap
    "base":    (0, 128, 64, 192),     # the plinth and the undersides
    "trim":    (64, 128, 128, 192),   # the bands between sections
}


def paint_case(img):
    """A housing panel: lit along the top, seamed at the bottom, LCARS on it."""
    x0, y0, x1, y1 = REGIONS["case"]
    img.rect(x0, y0, x1, y1, CASE)
    img.rect(x0, y0, x1, y0 + 2, CASE_LITE)
    img.rect(x0, y1 - 3, x1, y1, CASE_DEEP)
    img.rect(x0 + 5, y0 + 9, x1 - 5, y1 - 12, CASE_DEEP)
    img.rect(x0 + 7, y0 + 11, x1 - 7, y1 - 14, CASE)
    for i in range(4):
        yy = y0 + 14 + i * 9
        img.rect(x0 + 11, yy, x0 + 11 + 9 + (i % 3) * 4, yy + 4, BAR[i % len(BAR)])


def paint_plasma(img):
    """The column: bright up the middle, deep blue at the edges, banded.

    A gradient across the face rather than a flat colour, for the reason the
    replicator's emitter learned: a flat bright rectangle at this size reads
    as a hole cut in the model, not as something lit.
    """
    x0, y0, x1, y1 = REGIONS["plasma"]
    img.rect(x0, y0, x1, y1, PLASMA_LOW)
    w = x1 - x0
    for i in range(w):
        k = i / max(1, w - 1)
        f = max(0.0, 1.0 - abs(k - 0.5) * 2.0) ** 1.4
        if f > 0.55:
            c = tuple(int(PLASMA_MID[j] + (PLASMA[j] - PLASMA_MID[j])
                          * (f - 0.55) / 0.45) for j in range(3))
        else:
            c = tuple(int(PLASMA_LOW[j] + (PLASMA_MID[j] - PLASMA_LOW[j])
                          * f / 0.55) for j in range(3))
        img.rect(x0 + i, y0, x0 + i + 1, y1, c + (255,))
    # The banding. Dark rungs across the plasma: the one thing that says the
    # stuff is moving in a picture that cannot move.
    for yy in range(y0 + 3, y1 - 2, 9):
        img.rect(x0, yy, x1, yy + 2, PLASMA_LOW)
        img.rect(x0, yy + 2, x1, yy + 3, (58, 110, 172, 255))


def paint_collar(img):
    """The articulation collar, with the crystal lit behind its window."""
    x0, y0, x1, y1 = REGIONS["collar"]
    img.rect(x0, y0, x1, y1, CASE_DEEP)
    img.rect(x0, y0, x1, y0 + 3, CASE_LITE)
    img.rect(x0, y1 - 4, x1, y1, BASE_C)

    # the window
    wx0, wy0, wx1, wy1 = x0 + 14, y0 + 12, x1 - 14, y1 - 14
    img.rect(wx0 - 2, wy0 - 2, wx1 + 2, wy1 + 2, BLACK)
    img.rect(wx0, wy0, wx1, wy1, CRYSTAL_LO)
    # a faceted lozenge, drawn as rows: wide in the middle, points top and
    # bottom. Four straight lines is all a crystal ever needs.
    cx = (wx0 + wx1) // 2
    h = wy1 - wy0
    for i in range(h):
        k = i / max(1, h - 1)
        half = int((1.0 - abs(k - 0.42) * 2.1) * (wx1 - wx0) * 0.46)
        if half <= 0:
            continue
        shade = CRYSTAL if i % 5 else CRYSTAL_HI
        img.rect(cx - half, wy0 + i, cx + half, wy0 + i + 1, shade)
    img.rect(cx - 2, wy0 + 4, cx + 1, wy1 - 6, CRYSTAL_HI)


def paint_rest(img):
    x0, y0, x1, y1 = REGIONS["top"]
    img.rect(x0, y0, x1, y1, CASE)
    img.rect(x0 + 4, y0 + 4, x1 - 4, y1 - 4, CASE_LITE)
    img.rect(x0 + 9, y0 + 9, x1 - 9, y1 - 9, CASE_DEEP)
    img.rect(x0 + 14, y0 + 14, x1 - 14, y1 - 14, PLASMA_MID)
    img.rect(x0 + 20, y0 + 20, x1 - 20, y1 - 20, PLASMA)

    x0, y0, x1, y1 = REGIONS["base"]
    img.rect(x0, y0, x1, y1, BASE_C)
    img.rect(x0, y0, x1, y0 + 3, CASE_DEEP)
    img.rect(x0 + 6, y1 - 12, x1 - 6, y1 - 9, SKY)

    x0, y0, x1, y1 = REGIONS["trim"]
    img.rect(x0, y0, x1, y1, CASE_DEEP)
    img.rect(x0, y0 + 2, x1, y0 + 6, AMBER)
    img.rect(x0, y1 - 8, x1, y1 - 4, LILAC)


def build_atlas(path):
    img = Image(TEX_W, TEX_H, CASE_DEEP)
    paint_case(img)
    paint_plasma(img)
    paint_collar(img)
    paint_rest(img)
    img.save(path)


def ring(radius):
    """The eight corners of a prism, east/north, starting due east."""
    pts = []
    for i in range(SIDES):
        a = (i + 0.5) * 2 * math.pi / SIDES
        pts.append((radius * math.cos(a), radius * math.sin(a)))
    return pts


def drum(m, r0, r1, y0, y1, region):
    """The sides of a prism (or a frustum) between two heights."""
    P = m.place
    a, b = ring(r0), ring(r1)
    for i in range(SIDES):
        j = (i + 1) % SIDES
        ax, an = a[i]
        bx, bn = a[j]
        cx, cn = b[j]
        dx, dn = b[i]
        # The outward normal of the face, from the midpoint of its footprint.
        mx, mn = (ax + bx) / 2, (an + bn) / 2
        length = math.hypot(mx, mn) or 1.0
        m.quad(P(ax, an, y0), P(bx, bn, y0), P(cx, cn, y1), P(dx, dn, y1),
               region, P(mx / length, mn / length, 0))


def cap(m, radius, y, region, up=True):
    """A flat lid or floor, as a fan of triangles from the centre."""
    P = m.place
    pts = ring(radius)
    for i in range(SIDES):
        j = (i + 1) % SIDES
        ax, an = pts[i]
        bx, bn = pts[j]
        if up:
            m.tri(P(0, 0, y), P(ax, an, y), P(bx, bn, y), region, P(0, 0, 1))
        else:
            m.tri(P(0, 0, y), P(bx, bn, y), P(ax, an, y), region, P(0, 0, -1))


def build_mesh(path):
    m = MeshBuilder(TEX_W, TEX_H, up_axis=UP_AXIS)
    R = REGIONS

    # --- the plinth ------------------------------------------------------
    cap(m, R_BASE, 0.0, R["base"], up=False)
    drum(m, R_BASE, R_BASE, 0.0, H_BASE, R["base"])
    cap(m, R_BASE, H_BASE, R["trim"])

    # --- the lower housing, tapering in off the plinth --------------------
    drum(m, R_BASE, R_BODY, H_BASE, H_BASE + 0.06, R["trim"])
    drum(m, R_BODY, R_BODY, H_BASE + 0.06, H_LOWER, R["case"])
    cap(m, R_BODY, H_LOWER, R["trim"])

    # --- the column, in two runs with the collar between them -------------
    drum(m, R_CORE, R_CORE, H_LOWER, H_COL0, R["plasma"])
    drum(m, R_COLLAR, R_COLLAR, H_COL0, H_COL1, R["collar"])
    cap(m, R_COLLAR, H_COL0, R["trim"], up=False)
    cap(m, R_COLLAR, H_COL1, R["trim"])
    drum(m, R_CORE, R_CORE, H_COL1, H_UPPER, R["plasma"])

    # --- the upper housing and the cap ------------------------------------
    cap(m, R_BODY, H_UPPER, R["trim"], up=False)
    drum(m, R_BODY, R_BODY, H_UPPER, H_TOP - 0.06, R["case"])
    drum(m, R_BODY, R_BODY * 0.86, H_TOP - 0.06, H_TOP, R["trim"])
    cap(m, R_BODY * 0.86, H_TOP, R["top"])

    return m.emit(path, "TREKWarpCore", "TREK_WarpCore.png")


def preview(root, mesh, texture):
    """Renders it into design/art/warpcore/ on every run.

    Same two angles as the replicator: 270 looks straight at it and 225 is the
    three-quarter the game's camera actually shows. A model is judged from a
    picture, never from the source (DEV_GUIDE.md, "Render it and look").
    """
    out = os.path.join("design", "art", "warpcore")
    os.makedirs(out, exist_ok=True)
    tool = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "preview_model.py")
    for yaw, name in ((270, "front"), (225, "quarter")):
        target = os.path.join(out, f"preview_warpcore_{name}.png")
        subprocess.run([sys.executable, tool, mesh, texture, target, str(yaw)],
                       check=False)
    return out


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else "TrekShuttle/42"
    texture = os.path.join(root, "media", "textures", "TREK_WarpCore.png")
    mesh = os.path.join(root, "media", "models_X", "TREK_WarpCore.x")
    os.makedirs(os.path.dirname(texture), exist_ok=True)
    os.makedirs(os.path.dirname(mesh), exist_ok=True)
    build_atlas(texture)
    nv, nf = build_mesh(mesh)
    print(f"  TREK_WarpCore.x  {nv} verts, {nf} tris")
    print(f"  renders in {preview(root, mesh, texture)}")
    print("warp core model written")
