"""Generates the Borg among the dead (BORG.md): their look, their outfits.

    python tools/gen_borg.py [TrekShuttle/42]

The lore (LORE.md) already says what the horde is: Founder morphogenic virus
and Borg nanoprobes, grafted -- "a Collective with no Queen". Most of the dead
are only the virus's work. In a few the nanoprobes went on building, and those
are these: two outfits the engine hands out like any other, so the server
chooses them, the outfit id rides the zombie's own packet, and every client
dresses them with no mod code at all (CREW.md: a zombie's packet carries its
outfit id and nothing more).

  * **Assimilated** -- a Kentucky civilian in the clothes they died in, grey
    under the skin, with an eyepiece and a cranial plate, sometimes an arm.
  * **Drone** -- the nanoprobes finished: a black exosuit, armour grown over
    the chest, neck, shoulder and knee, the eyepiece, and the right forearm
    replaced by a tool.

Every piece is one of the engine's own three mechanisms, the same ones
TRAITS.md 4.6 uses for the species:

  * **Overlays** painted onto the body atlas (the exosuit, the grey skin), laid
    over whatever zombie skin is under them, as vanilla's T-shirt textures are.
  * **Vanilla armour rigs re-textured** -- the cuirass, gorget, articulated
    shoulder and knee pad. They are skinned, so they bend with the walk, and
    they are what gives a drone its bulk: this is the part that stops it
    being a reskin.
  * **Static meshes pinned to a bone** (the eyepiece and plate to Bip01_Head,
    the prosthetic to Bip01_R_Forearm), as vanilla's vambraces and bunny ears
    are. The prosthetic masks the right hand (CharacterMask part 6), as the
    ice-hockey gloves do, so the tool replaces the hand rather than growing
    through it.

**Where things go is measured, never guessed** (gen_species.py's rule): the
atlas is auto-packed and differs between the two bodies, so every texel is
given the bind-pose position, bone and bone-local position of the body
surface it lands on, and the meshes are built in each bone's own frame from
the body's own vertices. `tools/figure_render.py` then puts it all together
at a frame of the game's walk -- vanilla's vambrace and bunny ears first, to
prove the bone frames -- and writes the sheet it is judged on to
design/art/borg/.
"""
import math
import os
import random
import re
import sys
import uuid

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xskin  # noqa: E402
from meshbuild import MeshBuilder  # noqa: E402
from preview_model import parse_x  # noqa: E402
import figure_render as FR  # noqa: E402
from gen_species import merge_guid_table  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PZ = r"C:\Program Files (x86)\Steam\steamapps\common\ProjectZomboid\media"
SKINNED = os.path.join(PZ, "models_X", "Skinned")
CLOTHES = os.path.join(SKINNED, "Clothes")
PZTEX = os.path.join(PZ, "textures")
BODY_X = {"M": os.path.join(SKINNED, "MaleBody.x"), "F": os.path.join(SKINNED, "FemaleBody.x")}
BODY_TEX = {"M": "MaleBody0{}", "F": "FemaleBody0{}"}
SIZE = 256
GUID_NAMESPACE = "trekshuttle.clothing."
ART = os.path.join(ROOT, "design", "art", "borg")

# ---------------------------------------------------------------------------
# The palette. Near-black, not black: a character is read at about sixty
# pixels tall against grass, asphalt and night, and a true black garment loses
# its own shape (gen_uniform.py's BLACK, for the same reason).
# ---------------------------------------------------------------------------
SUIT = (25, 26, 30)
SUIT_RIB = (42, 44, 50)
SUIT_GROOVE = (14, 14, 17)
SUIT_CONDUIT = (70, 73, 80)
GLOVE = (19, 19, 22)
BOOT = (17, 17, 19)
PALLOR = (172, 177, 182)       # Borg grey, over the dead skin
VEIN = (48, 52, 60)
LIP = (120, 118, 124)
METAL_DARK = (50, 52, 58)
METAL = (74, 77, 84)
METAL_LIGHT = (128, 132, 140)
SEAM = (13, 13, 15)
TUBE_DARK = (22, 22, 25)
RED = (255, 38, 28)
GREEN = (70, 245, 120)

# The rigs a drone wears, re-textured. Bob's and Kate's share one texture, as
# every vanilla garment does, so each is painted from both.
RIGS = {
    "cuirass": ("Bob_Cuirass.x", "Kate_Cuirass.x", "Bob_Cuirass_ALT.x", "Kate_Cuirass_ALT.x"),
    "gorget": ("Bob_Gorget.x", "Kate_Gorget.x", None, None),
    "shoulder": ("Bob_ArticShoulder_L.x", "Kate_ArticShoulder_L.x",
                 "Bob_ArticShoulder_L_ALT.x", "Kate_ArticShoulder_L_ALT.x"),
    "knee": ("Bob_Kneepad_L.x", "Kate_Kneepad_L.x", "Bob_Kneepad_L_ALT.x", "Kate_Kneepad_L_ALT.x"),
}
HANDS = {"Bip01_L_Hand", "Bip01_R_Hand", "Bip01_L_Finger0", "Bip01_L_Finger1",
         "Bip01_R_Finger0", "Bip01_R_Finger1"}
FEET = {"Bip01_L_Foot", "Bip01_R_Foot", "Bip01_L_Toe0", "Bip01_R_Toe0"}
LIMBS = {"Bip01_L_UpperArm", "Bip01_R_UpperArm", "Bip01_L_Forearm", "Bip01_R_Forearm",
         "Bip01_L_Thigh", "Bip01_R_Thigh", "Bip01_L_Calf", "Bip01_R_Calf"}


def blend(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def hash01(*k):
    """Deterministic 0..1 from integers: every run paints the same drone."""
    n = 0x9E3779B1
    for v in k:
        n = ((n ^ (int(v) & 0xFFFFFFFF)) * 0x85EBCA6B) & 0xFFFFFFFF
        n ^= n >> 13
    n = (n * 0xC2B2AE35) & 0xFFFFFFFF
    return ((n ^ (n >> 16)) & 0xFFFF) / 65535.0


# ---------------------------------------------------------------------------
# The body, texel by texel (bind pose)
# ---------------------------------------------------------------------------
class BodyMap:
    """For every texel of one sex's body atlas: bind-pose position, the bone
    that moves it, and where it is in that bone's own frame."""

    def __init__(self, sex):
        self.sex = sex
        nodes = xskin.parse(BODY_X[sex])
        self.mesh = mesh = xskin.meshes(nodes)[0]
        self.dom = dom = mesh.dominant_bones()
        self.offset = {b: w[0] for b, w in mesh.weights.items()}
        self.pos = np.full((SIZE, SIZE, 3), np.nan)
        self.local = np.full((SIZE, SIZE, 3), np.nan)
        self.bone = np.full((SIZE, SIZE), "", dtype=object)
        for f in mesh.faces:
            bones = [dom[i] for i in f]
            bone = max(set(bones), key=bones.count)
            loc = [xskin.transform(mesh.verts[i], self.offset[bone]) for i in f]
            self._raster([mesh.uvs[i] for i in f], [mesh.verts[i] for i in f], loc, bone)
        self.covered = ~np.isnan(self.pos[..., 0])
        head = [i for i, b in enumerate(dom) if b == "Bip01_Head"]
        self.nose = mesh.verts[min(head, key=lambda i: mesh.verts[i][2])]
        self.eyes = self._find_eyes()

    def _raster(self, uv, pos, loc, bone):
        (ax, ay), (bx, by), (cx, cy) = [(u * SIZE, v * SIZE) for u, v in uv]
        d = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(d) < 1e-12:
            return
        for py in range(max(0, int(min(ay, by, cy))), min(SIZE - 1, int(max(ay, by, cy)) + 1) + 1):
            for px in range(max(0, int(min(ax, bx, cx))), min(SIZE - 1, int(max(ax, bx, cx)) + 1) + 1):
                x, y = px + 0.5, py + 0.5
                l1 = ((by - cy) * (x - cx) + (cx - bx) * (y - cy)) / d
                l2 = ((cy - ay) * (x - cx) + (ax - cx) * (y - cy)) / d
                l3 = 1 - l1 - l2
                if min(l1, l2, l3) < -0.03:
                    continue
                self.pos[py, px] = [l1 * pos[0][k] + l2 * pos[1][k] + l3 * pos[2][k] for k in range(3)]
                self.local[py, px] = [l1 * loc[0][k] + l2 * loc[1][k] + l3 * loc[2][k] for k in range(3)]
                self.bone[py, px] = bone

    def texels(self):
        ys, xs = np.nonzero(self.covered)
        for y, x in zip(ys, xs):
            yield x, y, self.pos[y, x], self.bone[y, x], self.local[y, x]

    def _find_eyes(self):
        """The eyes are the darkest pixels of the painted face either side of
        the nose, between it and the brow (gen_species.py's search, run on the
        bind pose so the result can go into the head's own frame)."""
        tex = Image.open(os.path.join(PZTEX, "Body", BODY_TEX[self.sex].format(1) + ".png")).convert("RGB")
        px = tex.load()
        n = self.nose
        sides = {-1: [], 1: []}
        for x, y, p, bone, _ in self.texels():
            if bone != "Bip01_Head" or p[2] > n[2] + 0.03 or not (n[1] + 0.008 < p[1] < n[1] + 0.035):
                continue
            if abs(p[0] - n[0]) < 0.008 or abs(p[0] - n[0]) > 0.045:
                continue
            r, g, b = px[int(x), int(y)]
            if r + g + b < 330:
                sides[1 if p[0] > n[0] else -1].append(p)
        eyes = {}
        for s in (-1, 1):
            if not sides[s]:
                raise SystemExit(f"{self.sex}: found no eye on side {s}")
            pts = sides[s]
            eyes[s] = tuple(sum(q[i] for q in pts) / len(pts) for i in range(3))
        # The wearer's left is +X (DEV_GUIDE: the rigs' own Bip01_L_* bones
        # sit at positive x).
        return {"L": eyes[1], "R": eyes[-1]}

    def verts_local(self, bone):
        o = self.offset[bone]
        return [xskin.transform(self.mesh.verts[i], o) for i, b in enumerate(self.dom) if b == bone]

    def to_local(self, p, bone):
        return xskin.transform(p, self.offset[bone])


# ---------------------------------------------------------------------------
# Veins: dark lines that wander across the surface from where the implants go
# ---------------------------------------------------------------------------
def grow_veins(bm, seeds, rng, steps=26, step=0.0055, branch=0.10):
    """Random walks snapped to the body surface, as polylines in bind space."""
    ok = bm.covered & np.isin(bm.bone, ["Bip01_Head", "Bip01_Neck"])
    surf = bm.pos[ok]
    lines = []
    stack = [(np.array(s, dtype=float), np.array(d, dtype=float), steps) for s, d in seeds]
    while stack:
        p, d, n = stack.pop()
        pts = [p]
        for _ in range(n):
            d = d + rng.normal(0, 0.55, 3)
            d /= np.linalg.norm(d)
            q = pts[-1] + d * step
            q = surf[np.argmin(((surf - q) ** 2).sum(axis=1))]
            if np.allclose(q, pts[-1]):
                break
            pts.append(q)
            if rng.random() < branch and n > 6:
                stack.append((q, d + rng.normal(0, 1.0, 3), int(n * 0.5)))
        if len(pts) > 1:
            lines.append(np.array(pts))
    return lines


def near_lines(p, lines, width):
    for pts in lines:
        a, b = pts[:-1], pts[1:]
        ab = b - a
        t = np.clip(((p - a) * ab).sum(axis=1) / np.maximum((ab * ab).sum(axis=1), 1e-12), 0, 1)
        d = np.linalg.norm(a + ab * t[:, None] - p, axis=1)
        if d.min() < width:
            return True
    return False


def vein_seeds(bm):
    """From the edge of the eyepiece (the left eye) and the temple where the
    cranial plate sits, out over the cheek, the brow and down the neck."""
    e = np.array(bm.eyes["L"])
    return [
        (e + (0.016, -0.004, 0.004), (0.2, -1, 0.1)),     # down the cheek
        (e + (0.014, 0.010, 0.006), (0.3, 1, 0.2)),       # up over the brow
        (e + (0.020, 0.000, 0.012), (1, -0.4, 0.8)),      # back to the ear
        (e + (0.022, -0.040, 0.030), (0.1, -1, 0.2)),     # jaw to neck
        (e + (-0.030, 0.012, 0.004), (-0.3, 0.6, 0.1)),   # a thread across the brow
    ]


# ---------------------------------------------------------------------------
# Overlays on the body atlas
# ---------------------------------------------------------------------------
def overlay_skin(bm, lines, pallor_alpha, vein_alpha):
    """Grey under the skin everywhere, and the veins."""
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    px = img.load()
    for x, y, p, bone, _ in bm.texels():
        if bone in ("Bip01_Head", "Bip01_Neck") and near_lines(p, lines, 0.0017):
            px[int(x), int(y)] = VEIN + (vein_alpha,)
        else:
            px[int(x), int(y)] = PALLOR + (pallor_alpha,)
    return dilate_alpha(img, bm.covered)


def overlay_suit(bm, lines):
    """The exosuit, collar to toe, over grey skin and veins on the head."""
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    px = img.load()
    greens = 0
    for x, y, p, bone, loc in bm.texels():
        x, y = int(x), int(y)
        if bone == "Bip01_Head":
            if near_lines(p, lines, 0.0017):
                px[x, y] = VEIN + (235,)
            else:
                px[x, y] = PALLOR + (185,)
            continue
        if bone == "Bip01_Neck":
            # The gorget covers most of it; what shows is ribbed hose.
            ph = (p[1] / 0.009) % 1.0
            px[x, y] = (SUIT_RIB if ph < 0.4 else SUIT_GROOVE) + (255,)
            continue
        if bone in HANDS:
            px[x, y] = blend(GLOVE, SUIT_RIB, 0.25 * hash01(x // 3, y // 3)) + (255,)
            continue
        if bone in FEET:
            px[x, y] = BOOT + (255,)
            continue
        if bone in LIMBS:
            # Corrugated along the limb (bone-local x runs down it), and one
            # conduit down its outer side.
            ph = (loc[0] / 0.016) % 1.0
            ang = math.atan2(loc[2], loc[1])
            if abs(math.sin(ang * 0.5 + 0.7)) < 0.16:
                c = SUIT_CONDUIT if (loc[0] / 0.008) % 1.0 < 0.6 else SUIT_GROOVE
            elif ph < 0.30:
                c = SUIT_RIB
            elif ph > 0.86:
                c = SUIT_GROOVE
            else:
                c = SUIT
            px[x, y] = c + (255,)
            continue
        # The torso: plates on a grid with dark seams, two ribbed conduits
        # down the front, and the odd green node.
        cx, cy = p[0] / 0.05, (p[1] - 0.01) / 0.045
        fx, fy = cx % 1.0, cy % 1.0
        cell = hash01(math.floor(cx), math.floor(cy), 7)
        c = SUIT if cell < 0.55 else blend(SUIT, METAL_DARK, 0.5)
        if min(fx, 1 - fx) < 0.06 or min(fy, 1 - fy) < 0.07:
            c = SEAM
        for tx in (-0.055, 0.058):
            if abs(p[0] - tx) < 0.011 and p[2] < 0:
                c = SUIT_RIB if (p[1] / 0.010) % 1.0 < 0.45 else SUIT_GROOVE
        if cell > 0.9 and abs(fx - 0.5) < 0.12 and abs(fy - 0.5) < 0.12:
            c = GREEN
            greens += 1
        px[x, y] = c + (255,)
    if greens < 3:
        raise SystemExit(f"{bm.sex}: the suit has {greens} green texels -- the node lights are gone")
    return dilate_alpha(img, bm.covered)


def dilate_alpha(img, covered, passes=3):
    """Bleed the painted islands outward so filtering along a seam never mixes
    in the transparent gutter (gen_uniform.py's dark fringe)."""
    a = np.array(img)
    have = a[..., 3] > 0
    for _ in range(passes):
        grow = a.copy()
        g2 = have.copy()
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            src = np.roll(np.roll(a, dy, 0), dx, 1)
            sh = np.roll(np.roll(have, dy, 0), dx, 1)
            take = sh & ~g2
            grow[take] = src[take]
            g2 |= take
        a, have = grow, g2
    return Image.fromarray(a, "RGBA")


# ---------------------------------------------------------------------------
# The armour rigs, re-textured
# ---------------------------------------------------------------------------
def surface(rig):
    """Every texel's bind position on a rig, and whether one lands there."""
    verts, faces, uvs = parse_x(os.path.join(CLOTHES, rig))
    pos = np.full((SIZE, SIZE, 3), np.nan)
    for f in faces:
        (ax, ay), (bx, by), (cx, cy) = [((uvs[i][0] % 1.0) * SIZE, (uvs[i][1] % 1.0) * SIZE) for i in f]
        d = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(d) < 1e-12:
            continue
        pa, pb, pc = (verts[i] for i in f)
        for py in range(max(0, int(min(ay, by, cy))), min(SIZE - 1, int(max(ay, by, cy)) + 1) + 1):
            for px in range(max(0, int(min(ax, bx, cx))), min(SIZE - 1, int(max(ax, bx, cx)) + 1) + 1):
                x, y = px + 0.5, py + 0.5
                l1 = ((by - cy) * (x - cx) + (cx - bx) * (y - cy)) / d
                l2 = ((cy - ay) * (x - cx) + (ax - cx) * (y - cy)) / d
                l3 = 1 - l1 - l2
                if min(l1, l2, l3) < -0.03:
                    continue
                pos[py, px] = [l1 * pa[k] + l2 * pb[k] + l3 * pc[k] for k in range(3)]
    return pos


def plating(p, kind):
    """Borg armour at one point of a rig: plates of three greys on an uneven
    grid, dark seams, ribbed hose across some plates, and green nodes."""
    x, y, z = p
    size = {"cuirass": 0.055, "gorget": 0.03, "shoulder": 0.035, "knee": 0.03}[kind]
    row = math.floor(y / size)
    # Stagger the columns row by row, so the seams do not line up into a grid.
    cx = (x + hash01(row, 3) * size) / (size * 1.3)
    col = math.floor(cx)
    fx, fy = cx % 1.0, (y / size) % 1.0
    h = hash01(col, row, len(kind))
    base = METAL_DARK if h < 0.45 else (METAL if h < 0.8 else SUIT)
    if min(fx, 1 - fx) < 0.07 or min(fy, 1 - fy) < 0.08:
        return SEAM
    if 0.55 < h < 0.72:
        return METAL_LIGHT if (x / 0.007) % 1.0 < 0.35 else TUBE_DARK
    if h > 0.93 and abs(fx - 0.5) < 0.14 and abs(fy - 0.5) < 0.14:
        return GREEN
    # A bevel: the top edge of each plate catches the light.
    if fy > 0.8:
        return blend(base, METAL_LIGHT, 0.35)
    return base


def rig_texture(kind):
    maps = [surface(RIGS[kind][0]), surface(RIGS[kind][1])]
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    px = img.load()
    covered = np.zeros((SIZE, SIZE), bool)
    for y in range(SIZE):
        for x in range(SIZE):
            for m in maps:
                if not np.isnan(m[y, x, 0]):
                    px[x, y] = plating(m[y, x], kind) + (255,)
                    covered[y, x] = True
                    break
    if covered.sum() < 500:
        raise SystemExit(f"{kind}: painted only {covered.sum()} texels -- the rig's UVs were not read")
    out = dilate_alpha(img, covered, 4)
    # Opaque everywhere: an armour texture has no holes, and a transparent
    # gutter texel sampled on a seam would show the body through the plate.
    a = np.array(out)
    a[..., 3] = 255
    return Image.fromarray(a, "RGBA")


# ---------------------------------------------------------------------------
# The hardware atlas the meshes are painted from (64x64, 16px cells)
# ---------------------------------------------------------------------------
CELL = {"dark": (0, 0), "metal": (16, 0), "black": (32, 0), "red": (48, 0),
        "green": (0, 16), "rib": (16, 16), "light": (32, 16), "redglow": (48, 16)}


def region(name):
    x, y = CELL[name]
    return (x + 1, y + 1, x + 15, y + 15)


def hardware_texture():
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 255))
    d = ImageDraw.Draw(img)
    fills = {"dark": METAL_DARK, "metal": METAL, "black": TUBE_DARK, "red": RED,
             "green": GREEN, "light": METAL_LIGHT, "redglow": (255, 150, 130)}
    for name, (x, y) in CELL.items():
        if name == "rib":
            for k in range(16):
                d.line([(x, y + k), (x + 15, y + k)], fill=(METAL if k % 4 < 2 else TUBE_DARK) + (255,))
            continue
        c = fills[name]
        for k in range(16):
            shade = 1.08 - 0.16 * k / 15
            d.line([(x, y + k), (x + 15, y + k)],
                   fill=tuple(min(255, int(v * shade)) for v in c) + (255,))
    return img


# ---------------------------------------------------------------------------
# Mesh helpers (any frame; normals from the winding)
# ---------------------------------------------------------------------------
def _n(v):
    m = math.sqrt(sum(c * c for c in v)) or 1.0
    return tuple(c / m for c in v)


def _sub(a, b):
    return tuple(a[i] - b[i] for i in range(3))


def _add(a, b):
    return tuple(a[i] + b[i] for i in range(3))


def _mul(a, s):
    return tuple(c * s for c in a)


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _dot(a, b):
    return sum(a[i] * b[i] for i in range(3))


def tri(mb, a, b, c, reg, uv=None, outward=None):
    """A triangle whose normal faces away from `outward` (a point inside)."""
    nrm = _n(_cross(_sub(b, a), _sub(c, a)))
    if outward is not None:
        centre = _mul(_add(_add(a, b), c), 1 / 3)
        if _dot(nrm, _sub(centre, outward)) < 0:
            b, c = c, b
            nrm = _mul(nrm, -1)
            if uv:
                uv = (uv[0], uv[2], uv[1])
    mb.tri(a, b, c, region(reg), nrm, uv)


def frame_of(axis):
    axis = _n(axis)
    ref = (0, 0, 1) if abs(axis[2]) < 0.9 else (1, 0, 0)
    u = _n(_cross(axis, ref))
    return axis, u, _cross(axis, u)


def ring(centre, axis, r, sides, phase=0.0):
    a, u, v = frame_of(axis)
    return [_add(centre, _add(_mul(u, r * math.cos(phase + 2 * math.pi * k / sides)),
                              _mul(v, r * math.sin(phase + 2 * math.pi * k / sides))))
            for k in range(sides)]


def tube(mb, pts, radii, sides, reg, cap_start=None, cap_end=None, rib=False):
    """A tube through `pts` (each with its own radius), optionally capped."""
    rings = []
    for i, p in enumerate(pts):
        prev, nxt = pts[max(0, i - 1)], pts[min(len(pts) - 1, i + 1)]
        rings.append(ring(p, _sub(nxt, prev), radii[i], sides))
    for i in range(len(pts) - 1):
        mid = _mul(_add(pts[i], pts[i + 1]), 0.5)
        for k in range(sides):
            k2 = (k + 1) % sides
            a, b, c, d = rings[i][k], rings[i][k2], rings[i + 1][k2], rings[i + 1][k]
            fv0, fv1 = (0.0, 1.0) if not rib else (0.0, 0.25)
            tri(mb, a, b, c, reg, ((0, fv0), (1, fv0), (1, fv1)), outward=mid)
            tri(mb, a, c, d, reg, ((0, fv0), (1, fv1), (0, fv1)), outward=mid)
    for idx, reg_cap in ((0, cap_start), (-1, cap_end)):
        if not reg_cap:
            continue
        rg = rings[idx]
        centre = pts[idx]
        inner = pts[1] if idx == 0 else pts[-2]
        for k in range(sides):
            tri(mb, centre, rg[k], rg[(k + 1) % sides], reg_cap, outward=inner)


def disc(mb, centre, axis, r, sides, reg, facing):
    rg = ring(centre, axis, r, sides)
    inside = _sub(centre, _mul(_n(facing), 0.01))
    for k in range(sides):
        tri(mb, centre, rg[k], rg[(k + 1) % sides], reg, outward=inside)


# ---------------------------------------------------------------------------
# The head implant (Bip01_Head's frame: +x up the neck, +y the wearer's left,
# +z out of the face)
# ---------------------------------------------------------------------------
def head_implant(bm):
    verts = bm.verts_local("Bip01_Head")
    arr = np.array(verts)
    centre = (arr.min(axis=0) + arr.max(axis=0)) / 2
    centre[0] = arr[:, 0].min() + 0.52 * (arr[:, 0].max() - arr[:, 0].min())
    eye = bm.to_local(bm.eyes["L"], "Bip01_Head")
    if eye[1] <= 0:
        raise SystemExit(f"{bm.sex}: the left eye is at head-local y {eye[1]:.3f}; "
                         f"expected +y for the wearer's left")
    front = arr[:, 2].max()
    mb = MeshBuilder(64, 64)

    def radius_towards(d):
        """How far the head reaches in direction d, from the centre."""
        rel = arr - centre
        dist = np.linalg.norm(rel, axis=1)
        cosang = (rel @ np.array(d)) / np.maximum(dist, 1e-9)
        near = cosang > math.cos(math.radians(28))
        return float((dist[near] * cosang[near]).max()) if near.any() else float(dist.max())

    # The eyepiece: a housing sunk into the socket, standing proud of the face,
    # with the red lens in its front.
    ez = max(eye[2], front - 0.02)
    ec = (eye[0] + 0.002, eye[1] - 0.002, ez)
    fwd = (0, 0, 1)
    body_r = 0.0195
    tube(mb, [_add(ec, (0, 0, -0.012)), _add(ec, (0, 0, 0.004)), _add(ec, (0, 0, 0.013))],
         [body_r * 0.9, body_r, body_r * 0.92], 8, "dark", cap_end="metal")
    disc(mb, _add(ec, (0, 0, 0.0142)), fwd, 0.0115, 8, "red", fwd)
    disc(mb, _add(ec, (0.002, 0.001, 0.0150)), fwd, 0.0045, 6, "redglow", fwd)
    # The emitter: a short barrel over the lens, angled out -- the eyepiece's
    # silhouette from the side, which is how it reads at a distance.
    em0 = _add(ec, (0.013, 0.010, 0.004))
    tube(mb, [em0, _add(em0, (0.004, 0.006, 0.018))], [0.0042, 0.0034], 6, "metal",
         cap_end="red")
    # The cranial plate: a shell over the left temple and the side of the
    # skull, conformed to the head, with two raised ribs across it.
    rows, cols = 7, 8
    grid = []
    for i in range(rows + 1):
        th = math.radians(18 + (98 - 18) * i / rows)          # from the crown down
        line = []
        for j in range(cols + 1):
            ph = math.radians(62 + (158 - 62) * j / cols)     # side to the back
            d = (math.cos(th), math.sin(th) * math.sin(ph), math.sin(th) * math.cos(ph))
            r = radius_towards(d) + 0.0065
            line.append(tuple(centre + np.array(d) * r))
        grid.append(line)
    inner = tuple(centre)
    for i in range(rows):
        for j in range(cols):
            a, b, c, d = grid[i][j], grid[i][j + 1], grid[i + 1][j + 1], grid[i + 1][j]
            reg = "metal" if (i + j) % 3 else "dark"
            if j in (2, 5):
                reg = "rib"
            tri(mb, a, b, c, reg, outward=inner)
            tri(mb, a, c, d, reg, outward=inner)
    # Its rim, so it has thickness and does not read as paint.
    rim = [grid[0][j] for j in range(cols + 1)] + [grid[i][cols] for i in range(1, rows + 1)] + \
          [grid[rows][j] for j in range(cols - 1, -1, -1)] + [grid[i][0] for i in range(rows - 1, 0, -1)]
    for k in range(len(rim)):
        a, b = rim[k], rim[(k + 1) % len(rim)]
        ia = tuple(centre + (np.array(a) - centre) * 0.955)
        ib = tuple(centre + (np.array(b) - centre) * 0.955)
        tri(mb, a, b, ib, "black", outward=inner)
        tri(mb, a, ib, ia, "black", outward=inner)
    # Green nodes on the plate.
    for (i, j) in ((2, 3), (4, 6)):
        p = grid[i][j]
        out = _n(_sub(p, inner))
        disc(mb, _add(p, _mul(out, 0.0012)), out, 0.0035, 6, "green", out)
    # Hoses: from the eyepiece round the temple into the plate, and from the
    # plate down behind the ear.
    start = _add(ec, (0.004, body_r * 0.9, -0.004))
    end = grid[4][0]
    mid = _add(_mul(_add(start, end), 0.5), (0.006, 0.014, 0.0))
    tube(mb, [start, mid, end], [0.0036] * 3, 6, "rib", rib=True)
    for j, dx in ((3, -0.045), (6, -0.050)):
        a = grid[rows][j]
        out = _n(_sub(a, inner))
        b = _add(_add(a, (dx * 0.5, 0, 0)), _mul(out, 0.004))
        c = _add(a, (dx, 0.0, -0.01))
        tube(mb, [a, b, c], [0.0042, 0.0042, 0.0038], 6, "rib", rib=True)
    return mb


# ---------------------------------------------------------------------------
# The prosthetic (Bip01_R_Forearm's frame: +x from the elbow to the wrist)
# ---------------------------------------------------------------------------
def arm_prosthetic(bm):
    fore = np.array(bm.verts_local("Bip01_R_Forearm"))
    x0, x1 = 0.012, float(fore[:, 0].max())
    cy, cz = float(np.median(fore[:, 1])), float(np.median(fore[:, 2]))
    rad = float(np.max(np.hypot(fore[:, 1] - cy, fore[:, 2] - cz)))
    axis = (1, 0, 0)
    mb = MeshBuilder(64, 64)
    c = lambda x: (x, cy, cz)
    R = rad + 0.010
    # The housing: an eight-sided sleeve swelling towards the wrist.
    tube(mb, [c(x0), c(x0 + 0.03), c(x1 - 0.02), c(x1)], [R * 0.85, R, R * 1.06, R * 0.98], 8, "dark",
         cap_start="black")
    # Ribs round it.
    for k in range(3):
        xr = x0 + 0.03 + k * (x1 - x0 - 0.05) / 2
        tube(mb, [c(xr), c(xr + 0.008)], [R * 1.12, R * 1.12], 8, "black", cap_start="black",
             cap_end="black")
    # A hose along its top, and two green nodes.
    top = (0, 0, R * 1.02)
    tube(mb, [_add(c(x0 + 0.01), top), _add(c((x0 + x1) / 2), _add(top, (0, 0, 0.006))),
              _add(c(x1 - 0.01), top)], [0.0045] * 3, 6, "rib", rib=True)
    for xn, ang in ((x0 + 0.05, 1.2), (x1 - 0.035, 2.4)):
        n = (0, math.cos(ang), math.sin(ang))
        p = _add(c(xn), _mul(n, R * 1.04))
        disc(mb, p, n, 0.005, 6, "green", n)
    # The wrist: a hexagonal block, and the tool: three claws round a probe.
    w0, w1 = x1, x1 + 0.035
    tube(mb, [c(w0), c(w1)], [R * 0.9, R * 0.8], 6, "metal", cap_end="dark")
    for k in range(3):
        ang = 2 * math.pi * k / 3 + 0.3
        dvec = (0, math.cos(ang), math.sin(ang))
        pts = [_add(c(w1), _mul(dvec, 0.020)), _add(c(w1 + 0.05), _mul(dvec, 0.026)),
               _add(c(w1 + 0.095), _mul(dvec, 0.012)), _add(c(w1 + 0.11), _mul(dvec, 0.002))]
        tube(mb, pts, [0.0060, 0.0055, 0.0040, 0.0015], 4, "light")
    tube(mb, [c(w1), c(w1 + 0.12)], [0.0035, 0.0022], 5, "metal", cap_end="red")
    return mb


# ---------------------------------------------------------------------------
# Previews
# ---------------------------------------------------------------------------
def static_parts(mb):
    return mb.verts, mb.faces, mb.uvs


def figure(sex, kind, anim, at, tex_dir, meshes, hw_path, zed=1):
    pose = FR.Pose(sex, anim, at)
    fig = FR.Figure(pose)
    skin = Image.open(os.path.join(PZTEX, "Body", f"{sex}_ZedBody0{zed}_level2.png")).convert("RGBA")
    if kind == "drone":
        skin.alpha_composite(Image.open(os.path.join(tex_dir["body"], f"borg_suit_{sex.lower()}.png")))
    elif kind == "assimilated":
        skin.alpha_composite(Image.open(os.path.join(tex_dir["body"], f"borg_skin_{sex.lower()}.png")))
    fig.body(skin)
    who = "Bob" if sex == "M" else "Kate"
    if kind == "assimilated":
        # What a Kentucky civilian died in: vanilla's own garments.
        fig.garment(os.path.join(CLOTHES, f"{who}_Trousers.x"),
                    tinted(os.path.join(PZTEX, "Clothes", "Trousers_Mesh", "Trousers_Denim.png"), (70, 90, 130)))
        fig.garment(os.path.join(CLOTHES, f"{who}_Jumper.x"),
                    os.path.join(PZTEX, "Clothes", "Jumper", "Jumper_Roundneck.png"))
    if kind in ("drone", "assimilated"):
        hv, hf, hu = static_parts(meshes[sex]["head"])
        fig.static(hv, hf, hu, hw_path, "Bip01_Head")
        av, af, au = static_parts(meshes[sex]["arm"])
        fig.static(av, af, au, hw_path, "Bip01_R_Forearm")
    if kind == "drone":
        for rig in ("cuirass", "gorget", "shoulder", "knee"):
            fig.garment(os.path.join(CLOTHES, RIGS[rig][0 if sex == "M" else 1]),
                        os.path.join(tex_dir["clothes"], f"borg_{rig}.png"))
    if kind == "vanilla":
        v, f, u = parse_x(os.path.join(PZ, "models_X", "Static", "Clothes", "Bob_Vambrace_BodyArmour_R.x"))
        fig.static(v, f, u, os.path.join(PZTEX, "Clothes", "Armor", "vambrace_bodyarmour_army.png"),
                   "Bip01_R_Forearm")
        v, f, u = parse_x(os.path.join(CLOTHES, "M_BunnyEars.X" if sex == "M" else "F_BunnyEars.X"))
        fig.static(v, f, u, os.path.join(PZTEX, "Clothes", "Hat", "bunnyears_black.png"), "Bip01_Head")
    return fig


def tinted(path, colour):
    """Vanilla's TINT garments are white; the game tints them per zombie."""
    img = Image.open(path).convert("RGBA")
    a = np.array(img).astype(np.float32)
    a[..., :3] *= np.array(colour, dtype=np.float32) / 255.0
    return Image.fromarray(a.astype(np.uint8), "RGBA")


def mask_hand(fig, sex):
    """The prosthetic's m_Masks 6: the right hand is not drawn."""
    pos, faces, uvs, tex = fig.parts[0]
    dom = fig.pose.body.dominant_bones()
    hand = {"Bip01_R_Hand", "Bip01_R_Finger0", "Bip01_R_Finger1"}
    keep = np.array([not all(dom[i] in hand for i in f) for f in faces])
    fig.parts[0] = (pos, faces[keep], uvs, tex)


def sheet(tex_dir, meshes, hw_path, anim):
    os.makedirs(ART, exist_ok=True)
    rows = []
    for sex in ("M", "F"):
        cells = []
        for kind in ("vanilla", "assimilated", "drone"):
            fig = figure(sex, kind, anim, 0.3, tex_dir, meshes, hw_path)
            if kind != "vanilla":
                mask_hand(fig, sex)
            for yaw in (-35, 35, 150):
                cells.append(FR.render(fig, 300, yaw, 12))
        rows.append(cells)
    w = 300 * len(rows[0])
    img = Image.new("RGB", (w, 300 * len(rows)), (28, 30, 36))
    for r, cells in enumerate(rows):
        for c, cell in enumerate(cells):
            img.paste(cell, (c * 300, r * 300))
    out = os.path.join(ART, "borg_sheet.png")
    img.save(out)
    print("sheet ->", out)
    return out


def game_scale(tex_dir, meshes, hw_path, anim):
    """What the game really shows: a character about 64 and 100 pixels tall,
    seen from the isometric camera, on grass, asphalt and at night."""
    grounds = [(78, 96, 52), (72, 72, 76), (18, 20, 30)]
    figs = []
    for sex in ("M", "F"):
        for kind in ("vanilla", "assimilated", "drone"):
            fig = figure(sex, kind, anim, 0.3, tex_dir, meshes, hw_path)
            if kind != "vanilla":
                mask_hand(fig, sex)
            figs.append(fig)
    out_rows = []
    for px_tall in (64, 100):
        for g in grounds:
            row = Image.new("RGB", (len(figs) * (px_tall + 20), px_tall + 30), g)
            for i, fig in enumerate(figs):
                im = FR.render(fig, px_tall + 20, 45, 30, bg=g, height=px_tall, ss=4)
                if g == grounds[2]:
                    im = Image.eval(im, lambda v: int(v * 0.55))
                row.paste(im, (i * (px_tall + 20), 5))
            out_rows.append(row)
    w = max(r.width for r in out_rows)
    img = Image.new("RGB", (w, sum(r.height for r in out_rows)), (0, 0, 0))
    y = 0
    for r in out_rows:
        img.paste(r, (0, y))
        y += r.height
    out = os.path.join(ART, "borg_game_scale.png")
    img.save(out)
    print("game scale ->", out)
    return out


# ---------------------------------------------------------------------------
# Driving it
# ---------------------------------------------------------------------------
def build_art(root):
    tex_body = os.path.join(root, "media", "textures", "Body", "trek")
    tex_clothes = os.path.join(root, "media", "textures", "Clothes", "trek")
    models = os.path.join(root, "media", "models_X", "Skinned", "Clothes")
    for d in (tex_body, tex_clothes, models):
        os.makedirs(d, exist_ok=True)
    rng = np.random.default_rng(1701)
    meshes = {}
    for sex in ("M", "F"):
        bm = BodyMap(sex)
        lines = grow_veins(bm, vein_seeds(bm), rng)
        overlay_suit(bm, lines).save(os.path.join(tex_body, f"borg_suit_{sex.lower()}.png"), optimize=True)
        overlay_skin(bm, lines, 135, 200).save(os.path.join(tex_body, f"borg_skin_{sex.lower()}.png"),
                                               optimize=True)
        head, arm = head_implant(bm), arm_prosthetic(bm)
        head.emit(os.path.join(models, f"TREK_BorgHead_{sex}.X"), f"TREK_BorgHead_{sex}",
                  "borg_hardware.png", frame_name=f"TREK_BorgHead_{sex}")
        arm.emit(os.path.join(models, f"TREK_BorgArm_{sex}.X"), f"TREK_BorgArm_{sex}",
                 "borg_hardware.png", frame_name=f"TREK_BorgArm_{sex}")
        meshes[sex] = {"head": head, "arm": arm}
        print(f"  {sex}: eyes {[tuple(round(c, 3) for c in e) for e in bm.eyes.values()]}, "
              f"{len(lines)} veins, head implant {len(head.faces)} faces, arm {len(arm.faces)} faces")
    hardware_texture().save(os.path.join(tex_clothes, "borg_hardware.png"))
    for rig in RIGS:
        rig_texture(rig).save(os.path.join(tex_clothes, f"borg_{rig}.png"), optimize=True)
    return {"body": tex_body, "clothes": tex_clothes}, meshes, os.path.join(tex_clothes, "borg_hardware.png")


# ---------------------------------------------------------------------------
# Clothing XMLs, GUID rows, item scripts, the outfits
# ---------------------------------------------------------------------------
def guid(stem):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, GUID_NAMESPACE + stem))


def garments():
    """Every Borg garment: its clothing XML and the item that carries it.

    All hidden -- vanilla's inventory pane skips a hidden item ("they are just
    equipped models", ISInventoryPane.lua), so a Borg's corpse shows its loot
    and not its implants -- and none carries a defence stat."""
    g = {}
    for sex in ("M", "F"):
        g[f"TrekBorg_Suit_{sex}"] = dict(base=rf"body\trek\borg_suit_{sex.lower()}", loc="zeddmg")
        g[f"TrekBorg_Skin_{sex}"] = dict(base=rf"body\trek\borg_skin_{sex.lower()}", loc="zeddmg")
    # The head implant is a hat to the engine: ItemVisuals.findHat takes the
    # first item with a hat category, and HairStyles.getAlternateForHat
    # answers "nohairnobeard" with no hair at all. Drones are bald.
    g["TrekBorg_Head"] = dict(model="TREK_BorgHead", bone="Bip01_Head", tex=r"clothes\trek\borg_hardware",
                              hat="nohairnobeard", loc="zeddmg")
    # The prosthetic hides the right hand (CharacterMask part 6), as vanilla's
    # ice-hockey gloves hide both hands: the tool replaces it.
    g["TrekBorg_Arm"] = dict(model="TREK_BorgArm", bone="Bip01_R_Forearm", tex=r"clothes\trek\borg_hardware",
                             masks=[6], loc="zeddmg")
    for rig, loc in (("cuirass", "cuirass"), ("gorget", "gorget"), ("shoulder", "shoulderpadleft"),
                     ("knee", "knee_left")):
        g[f"TrekBorg_{rig.capitalize()}"] = dict(rig=RIGS[rig], tex=rf"clothes\trek\borg_{rig}", loc=loc)
    return g


def write_xml(root, stem, spec):
    lines = ['<?xml version="1.0" encoding="utf-8"?>',
             "<!-- Generated by tools/gen_borg.py (BORG.md). -->", "<clothingItem>"]
    alt_m = alt_f = ""
    if "model" in spec:
        male = rf"media\models_X\Skinned\Clothes\{spec['model']}_M.X"
        female = rf"media\models_X\Skinned\Clothes\{spec['model']}_F.X"
    elif "rig" in spec:
        bob, kate, bob_alt, kate_alt = spec["rig"]
        male, female = rf"media\models_X\Skinned\Clothes\{bob}", rf"media\models_X\Skinned\Clothes\{kate}"
        alt_m = rf"media\models_X\Skinned\Clothes\{bob_alt}" if bob_alt else ""
        alt_f = rf"media\models_X\Skinned\Clothes\{kate_alt}" if kate_alt else ""
    else:
        male = female = ""
    lines += [f"\t<m_MaleModel>{male}</m_MaleModel>", f"\t<m_FemaleModel>{female}</m_FemaleModel>"]
    if alt_m or alt_f:
        lines += [f"\t<m_AltMaleModel>{alt_m}</m_AltMaleModel>",
                  f"\t<m_AltFemaleModel>{alt_f}</m_AltFemaleModel>"]
    lines += [f"\t<m_GUID>{guid(stem)}</m_GUID>", "\t<m_Static>false</m_Static>",
              "\t<m_AllowRandomHue>false</m_AllowRandomHue>", "\t<m_AllowRandomTint>false</m_AllowRandomTint>",
              f"\t<m_AttachBone>{spec.get('bone', '')}</m_AttachBone>"]
    if spec.get("hat"):
        lines.append(f"\t<m_HatCategory>{spec['hat']}</m_HatCategory>")
    for m in spec.get("masks", []):
        lines.append(f"\t<m_Masks>{m}</m_Masks>")
    if male:
        lines.append("\t<m_MasksFolder>none</m_MasksFolder>")
    if spec.get("base"):
        lines.append(f"\t<m_BaseTextures>{spec['base']}</m_BaseTextures>")
    if spec.get("tex"):
        lines.append(f"\t<textureChoices>{spec['tex']}</textureChoices>")
    lines.append("</clothingItem>")
    path = os.path.join(root, "media", "clothing", "clothingItems", stem + ".xml")
    with open(path, "w", encoding="utf-8", newline="\r\n") as fh:
        fh.write("\n".join(lines) + "\n")
    return f"media/clothing/clothingItems/{stem}.xml", guid(stem)


def write_script(root, specs):
    out = ["module TrekShuttle", "{",
           "    /*  The Borg among the dead (BORG.md), generated by tools/gen_borg.py.",
           "        Hidden: what a Borg wears, never loot. No defence stats.",
           "    */", ""]
    for stem, spec in specs.items():
        out += [f"    item {stem}", "    {", "        DisplayCategory = Appearance,",
                "        ItemType = base:clothing,", f"        BodyLocation = base:{spec['loc']},",
                f"        ClothingItem = {stem},", "        WorldRender = false,", "        hidden = true,",
                "    }", ""]
    out.append("}")
    with open(os.path.join(root, "media", "scripts", "trekborg.txt"), "w", encoding="utf-8",
              newline="\r\n") as fh:
        fh.write("\n".join(out) + "\n")


NAMES = {"Suit": "Borg Exosuit", "Skin": "Borg Nanoprobe Pallor", "Head": "Borg Cranial Implant",
         "Arm": "Borg Prosthetic", "Cuirass": "Borg Chest Armour", "Gorget": "Borg Neck Armour",
         "Shoulder": "Borg Shoulder Armour", "Knee": "Borg Knee Armour"}


def write_names(root, specs):
    """Adds the items' names to ItemName.json, keeping every other entry."""
    import json
    path = os.path.join(root, "media", "lua", "shared", "Translate", "EN", "ItemName.json")
    data = json.load(open(path, encoding="utf-8"))
    for stem in specs:
        data[f"TrekShuttle.{stem}"] = NAMES[stem.split("_")[1]]
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(data, indent=4, ensure_ascii=False) + "\n")


# What an assimilated civilian died in: vanilla's own Generic03 for their sex
# (a top, jeans, socks and trainers), without anything that would sit where an
# implant goes -- hats, glasses, earrings, a nose stud, a necklace, a bangle.
DROP = re.compile(r"^(Hat_|Glasses_|Earring_|NoseStud_|Necklace_|Bracelet_)")


def vanilla_outfit(sex, name):
    src = open(os.path.join(PZ, "clothing", "clothing.xml"), encoding="utf-8-sig").read()
    tag = "m_MaleOutfits" if sex == "M" else "m_FemaleOutfits"
    for block in re.findall(rf"<{tag}>(.*?)</{tag}>", src, re.S):
        if re.search(rf"<m_Name>{name}</m_Name>", block):
            break
    else:
        raise SystemExit(f"vanilla has no {sex} outfit {name}")
    g2n = {}
    folder = os.path.join(PZ, "clothing", "clothingItems")
    for f in os.listdir(folder):
        t = open(os.path.join(folder, f), encoding="utf-8-sig", errors="replace").read()
        m = re.search(r"<m_GUID>(.*?)</m_GUID>", t)
        if m:
            g2n[m.group(1).strip()] = f[:-4]
    flags = dict(re.findall(r"<m_(Top|Pants|AllowPantsHue|AllowTopTint|AllowTShirtDecal)>(\w+)<", block))
    items, dropped = [], 0
    for it in re.findall(r"<m_items>(.*?)</m_items>", block, re.S):
        names = [g2n.get(g.strip(), "") for g in re.findall(r"<itemGUID>(.*?)</itemGUID>", it)]
        if any(DROP.match(n) for n in names):
            dropped += 1
            continue
        items.append("\t\t<m_items>" + it + "</m_items>")
    # Both sides of the filter need a floor (DEV_GUIDE: a check against an
    # empty set is not a passing check).
    if len(items) < 3 or dropped < 2:
        raise SystemExit(f"{name} ({sex}): kept {len(items)}, dropped {dropped} -- the parse has "
                         f"stopped matching vanilla's clothing.xml")
    return flags, items


def item_block(stem, probability=None):
    p = f"\n\t\t\t<probability>{probability}</probability>" if probability is not None else ""
    return f"\t\t<m_items>{p}\n\t\t\t<itemGUID>{guid(stem)}</itemGUID>\n\t\t</m_items>"


def outfit_xml(tag, name, sex, flags, items):
    f = {"Top": "false", "Pants": "false", "AllowPantsHue": "false", "AllowTopTint": "false",
         "AllowTShirtDecal": "false"}
    f.update(flags)
    lines = [f"\t<{tag}>", f"\t\t<m_Name>{name}</m_Name>",
             f"\t\t<m_Guid>{guid('outfit.' + name + '.' + sex)}</m_Guid>"]
    lines += [f"\t\t<m_{k}>{v}</m_{k}>" for k, v in f.items()]
    lines += items + [f"\t</{tag}>"]
    return "\n".join(lines)


# The two outfits' names: TREK_Borg.lua spawns and recognises them by these.
DRONE, ASSIMILATED = "TrekBorgDrone", "TrekBorgAssimilated"


def outfit_blocks():
    out = []
    for sex, tag in (("M", "m_MaleOutfits"), ("F", "m_FemaleOutfits")):
        drone = [item_block(f"TrekBorg_Suit_{sex}"), item_block("TrekBorg_Head"),
                 item_block("TrekBorg_Arm", 0.75), item_block("TrekBorg_Cuirass", 0.9),
                 item_block("TrekBorg_Gorget"), item_block("TrekBorg_Shoulder", 0.55),
                 item_block("TrekBorg_Knee", 0.5)]
        out.append(outfit_xml(tag, DRONE, sex, {}, drone))
        flags, civvies = vanilla_outfit(sex, "Generic03")
        mine = [item_block(f"TrekBorg_Skin_{sex}"), item_block("TrekBorg_Head"),
                item_block("TrekBorg_Arm", 0.3), item_block("TrekBorg_Gorget", 0.2)]
        out.append(outfit_xml(tag, ASSIMILATED, sex, flags, civvies + mine))
    return out


BEGIN = "<!-- gen_borg.py: the Borg outfits (BORG.md). Generated up to the end marker. -->"
END = "<!-- gen_borg.py: end -->"


def write_outfits(root):
    """The outfits go in the mod's common clothing.xml, beside the crew's
    empty one, inside markers so a rerun replaces only its own."""
    common = os.path.join(os.path.dirname(os.path.abspath(root)), "common", "media", "clothing", "clothing.xml")
    src = open(common, encoding="utf-8").read().replace("\r\n", "\n")
    if BEGIN in src:
        src = src[:src.index(BEGIN)].rstrip("\t ") + src[src.index(END) + len(END):].lstrip("\n")
    at = src.rindex("</outfitManager>")
    src = src[:at] + "\t" + BEGIN + "\n" + "\n".join(outfit_blocks()) + "\n\t" + END + "\n" + src[at:]
    with open(common, "w", encoding="utf-8", newline="\r\n") as fh:
        fh.write(src)


def build_clothing(root):
    specs = garments()
    rows = [write_xml(root, stem, spec) for stem, spec in specs.items()]
    merge_guid_table(root, rows)
    write_script(root, specs)
    write_names(root, specs)
    write_outfits(root)
    print(f"  {len(specs)} garments with their XMLs, GUID rows and items; 4 outfits")


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "TrekShuttle", "42")
    tex_dir, meshes, hw = build_art(root)
    build_clothing(root)
    anim = os.environ.get("BORG_ANIM", "Bob_Walk.x")
    sheet(tex_dir, meshes, hw, anim)
    game_scale(tex_dir, meshes, hw, anim)
