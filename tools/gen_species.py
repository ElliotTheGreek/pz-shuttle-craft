"""Generates what each species looks like (TRAITS.md 2.4).

    python tools/gen_species.py TrekShuttle/42

Three kinds of look, each the engine's own mechanism:

  **Skins** -- media/textures/Body/TREK_<Species>_<M|F><1-5>.png. Vanilla's
  five skin tones recoloured; HumanVisual.setSkinTextureName points the body
  at one, and getSkinTexture() answers the name before it ever looks at the
  five-tone list (bytecode, bci 0-11). The engine loads it as
  media/textures/Body/<name>.png (ModelInstanceTextureCreator's recipe).
  Andorian blue, Orion green, an android's pale gold.

  **Overlays** -- a 256x256 RGBA laid over the skin by a hidden body-visual
  item, exactly as vanilla's stubble and makeup are: a clothing item with no
  model and an m_BaseTextures. Trill spots, Bajoran nose ridges, Betazoid
  eyes, a Klingon brow, a Talaxian's mottling, a Borg implant.

  **Meshes** -- a static model pinned to Bip01_Head, as vanilla's bunny ears
  are (M_BunnyEars.X has no skin weights; the XML's m_AttachBone places it).
  Vulcan ears, Andorian antennae. Five textureChoices each, one per skin tone,
  chosen by the server with ItemVisual.setTextureChoice.

**Where things go is measured, never guessed.** The body texture is an
auto-packed atlas, and the male and female bodies are packed differently
(the crown is at u 0.79 on one and 0.52 on the other). So every texel is
given the bind-pose position of the body surface it lands on, by rasterising
the mesh's own triangles in UV space -- gen_uniform.py's method -- and every
feature is decided from anatomy found in the same mesh: the nose is the
head's foremost vertex, the crown its highest, the eyes the dark pixels of
the painted face. Head space (for the meshes) is the Bip01_Head bone's own:
+x up the neck, +z out of the face, y to the sides; the head runs from the
neck at x 0 to the crown at about 0.15, and the bunny ears sit at x
0.09-0.28 in exactly that frame.
"""
import math
import os
import random
import sys
import uuid

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xskin  # noqa: E402
from meshbuild import MeshBuilder  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PZ = r"C:\Program Files (x86)\Steam\steamapps\common\ProjectZomboid\media"
BODY_X = {"M": os.path.join(PZ, "models_X", "Skinned", "MaleBody.x"),
          "F": os.path.join(PZ, "models_X", "Skinned", "FemaleBody.x")}
BODY_TEX = {"M": "MaleBody0{}", "F": "FemaleBody0{}"}
SIZE = 256
GUID_NAMESPACE = "trekshuttle.clothing."

# The skin each recoloured species gets, at vanilla's lightest tone; darker
# tones keep their own shading ratio against it.
SKINS = {
    "Andorian": (120, 170, 225),
    "Orion": (95, 175, 100),
    "Android": (238, 226, 190),
}
# How far a skin moves towards its target: an android is pale gold, not
# painted.
SKIN_STRENGTH = {"Andorian": 1.0, "Orion": 1.0, "Android": 0.85}

OVERLAYS = ["trill", "bajoran", "betazoid", "klingon", "talaxian", "exborg"]
MESHES = ["vulcanears", "antennae"]


# ---------------------------------------------------------------------------
# The body, texel by texel
# ---------------------------------------------------------------------------
class Body:
    """Bind-pose positions for every texel of one sex's body texture."""

    def __init__(self, sex):
        nodes = xskin.parse(BODY_X[sex])
        sk = xskin.Skeleton(nodes)
        mesh = xskin.meshes(nodes)[0]
        world = sk.world()
        pos = mesh.skin(world)
        dom = mesh.dominant_bones()
        self.sex = sex
        self.pos = [[None] * SIZE for _ in range(SIZE)]
        for a, b, c in mesh.faces:
            self._raster(mesh.uvs[a], mesh.uvs[b], mesh.uvs[c], pos[a], pos[b], pos[c])
        head = [i for i, bone in enumerate(dom) if bone == "Bip01_Head"]
        self.nose = pos[min(head, key=lambda i: pos[i][2])]
        self.crown = pos[max(head, key=lambda i: pos[i][1])]
        self.half = max(abs(pos[i][0]) for i in head)
        # Head space, for the meshes: the ear is the widest head vertex.
        off = mesh.weights["Bip01_Head"][0]
        local = [xskin.transform(mesh.verts[i], off) for i in head]
        self.ear_local = max(local, key=lambda p: abs(p[1]))
        self.crown_local = max(local, key=lambda p: p[0])
        self.head_local_top = max(p[0] for p in local)
        self.eyes = self._find_eyes()

    def _raster(self, ua, ub, uc, pa, pb, pc):
        ax, ay = ua[0] * SIZE, ua[1] * SIZE
        bx, by = ub[0] * SIZE, ub[1] * SIZE
        cx, cy = uc[0] * SIZE, uc[1] * SIZE
        d = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(d) < 1e-12:
            return
        for py in range(max(0, int(min(ay, by, cy))), min(SIZE - 1, int(max(ay, by, cy)) + 1) + 1):
            for px in range(max(0, int(min(ax, bx, cx))), min(SIZE - 1, int(max(ax, bx, cx)) + 1) + 1):
                x, y = px + 0.5, py + 0.5
                l1 = ((by - cy) * (x - cx) + (cx - bx) * (y - cy)) / d
                l2 = ((cy - ay) * (x - cx) + (ax - cx) * (y - cy)) / d
                l3 = 1 - l1 - l2
                if min(l1, l2, l3) < -0.02:
                    continue
                self.pos[py][px] = tuple(l1 * pa[i] + l2 * pb[i] + l3 * pc[i] for i in range(3))

    def texels(self):
        for y in range(SIZE):
            for x in range(SIZE):
                p = self.pos[y][x]
                if p is not None:
                    yield x, y, p

    def _find_eyes(self):
        """The two eyes: the darkest pixels of the painted face, one cluster
        either side of the nose, between the nose and the brow."""
        tex = Image.open(os.path.join(PZ, "textures", "Body",
                                      BODY_TEX[self.sex].format(1) + ".png")).convert("RGB")
        px = tex.load()
        n = self.nose
        sides = {-1: [], 1: []}
        for x, y, p in self.texels():
            if p[2] > n[2] + 0.03 or not (n[1] + 0.008 < p[1] < n[1] + 0.035):
                continue
            if abs(p[0] - n[0]) < 0.008 or abs(p[0] - n[0]) > self.half * 0.7:
                continue
            r, g, b = px[x, y]
            if r + g + b < 330:
                sides[1 if p[0] > n[0] else -1].append(p)
        eyes = []
        for s in (-1, 1):
            pts = sides[s]
            if not pts:
                raise SystemExit(f"{self.sex}: found no eye on side {s} -- the face search "
                                 f"is looking in the wrong place")
            eyes.append(tuple(sum(q[i] for q in pts) / len(pts) for i in range(3)))
        return eyes


def dist(a, b):
    return math.sqrt(sum((a[i] - b[i]) ** 2 for i in range(3)))


# ---------------------------------------------------------------------------
# Skins
# ---------------------------------------------------------------------------
def recolour(src, target, strength):
    """Moves skin towards `target`, keeping each pixel's shading. Eye whites
    and dark detail (pupils, brows) are left alone: they are not skin."""
    img = src.convert("RGBA")
    px = img.load()
    w, h = img.size
    lums = sorted(0.299 * px[x, y][0] + 0.587 * px[x, y][1] + 0.114 * px[x, y][2]
                  for y in range(0, h, 4) for x in range(0, w, 4))
    ref = lums[len(lums) // 2] or 1
    tref = 0.299 * target[0] + 0.587 * target[1] + 0.114 * target[2]
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            lum = 0.299 * r + 0.587 * g + 0.114 * b
            sat = (max(r, g, b) - min(r, g, b)) / (max(r, g, b) or 1)
            if sat < 0.08 or lum < 45:
                continue
            k = lum / ref
            nr, ng, nb = (min(255, c * k * (ref / tref) * (tref / ref)) for c in target)
            nr, ng, nb = (int(o + (n - o) * strength) for o, n in ((r, nr), (g, ng), (b, nb)))
            px[x, y] = (nr, ng, nb, a)
    return img


def skins(out_dir):
    made = []
    for species, target in SKINS.items():
        for sex in ("M", "F"):
            for tone in range(1, 6):
                src = Image.open(os.path.join(PZ, "textures", "Body",
                                              BODY_TEX[sex].format(tone) + ".png"))
                # Each darker tone keeps its darkness against the target.
                img = recolour(src, target, SKIN_STRENGTH[species])
                path = os.path.join(out_dir, f"TREK_{species}_{sex}{tone}.png")
                img.save(path, optimize=True)
                made.append(path)
    return made


# ---------------------------------------------------------------------------
# Overlays
# ---------------------------------------------------------------------------
def overlay(body, kind, rng):
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    px = img.load()
    n, c, half = body.nose, body.crown, body.half
    eye_y = sum(e[1] for e in body.eyes) / 2

    if kind == "trill":
        # A band of spots from each temple down the side of the neck.
        centres = []
        for s in (-1, 1):
            band = [p for _, _, p in body.texels()
                    if s * (p[0] - n[0]) > half * 0.62
                    and n[1] - 0.075 < p[1] < eye_y + 0.022
                    and p[2] > n[2] + 0.035]
            rng.shuffle(band)
            chosen = []
            for p in band:
                if all(dist(p, q) > 0.009 for q in chosen):
                    chosen.append(p)
                if len(chosen) >= 24:
                    break
            centres += [(p, 0.0035 + 0.0025 * rng.random()) for p in chosen]
        for x, y, p in body.texels():
            for q, r in centres:
                d = dist(p, q)
                if d < r:
                    a = 220 if d < r * 0.75 else 140
                    px[x, y] = (95, 55, 30, a)
                    break

    elif kind == "bajoran":
        # Four short ridges across the bridge of the nose.
        for x, y, p in body.texels():
            # The face is about forty texels square in this atlas, so the
            # bridge of the nose is two or three texels wide: the ridges are
            # alternate rows of it, and that is all the resolution there is.
            if abs(p[0] - n[0]) < 0.014 and p[2] < n[2] + 0.026 and n[1] + 0.003 < p[1] < eye_y:
                f = ((eye_y - p[1]) / 0.0055) % 1.0
                if f < 0.45:
                    px[x, y] = (115, 70, 50, 190)

    elif kind == "betazoid":
        # Wholly dark eyes: the eye's own pixels, darkened to near black.
        for x, y, p in body.texels():
            for e in body.eyes:
                if dist(p, e) < 0.0045:
                    px[x, y] = (12, 10, 14, 240)
                    break

    elif kind == "klingon":
        # A crest up the middle of the forehead and three bold ridges either
        # side of it, curving down towards the temples. The forehead only:
        # the ridges are a brow, not a helmet.
        top = eye_y + 0.048
        for x, y, p in body.texels():
            if p[2] > n[2] + 0.032 or p[1] < eye_y + 0.005 or p[1] > top:
                continue
            ax = abs(p[0] - n[0])
            if ax > half * 0.8:
                continue
            if ax < 0.0035:
                px[x, y] = (75, 42, 25, 190)
                continue
            f = ((p[1] - eye_y - 0.005) + ax * 0.35) / 0.0115
            ring = f % 1.0
            if f < 3.3:
                if ring < 0.30:
                    px[x, y] = (75, 42, 25, 165)
                elif ring < 0.45:
                    px[x, y] = (255, 225, 195, 70)

    elif kind == "talaxian":
        # Mottling over the scalp and down the back of the head: scattered
        # blotches in two browns, with the skin showing between them.
        pool = [t[2] for t in body.texels() if t[2][1] > eye_y + 0.012]
        blobs = []
        for p in rng.sample(pool, min(len(pool), 600)):
            if all(dist(p, q) > 0.011 for q, _, _ in blobs):
                blobs.append((p, 0.0035 + 0.004 * rng.random(), rng.random() < 0.5))
            if len(blobs) >= 70:
                break
        for x, y, p in body.texels():
            if p[1] < eye_y + 0.008:
                continue
            for q, r, dark in blobs:
                if dist(p, q) < r:
                    px[x, y] = (140, 70, 30, 170) if dark else (190, 115, 55, 150)
                    break

    elif kind == "exborg":
        # An implant round one eye and a line of it down the cheek.
        e = body.eyes[0]
        for x, y, p in body.texels():
            d = dist(p, e)
            if d < 0.0040:
                px[x, y] = (235, 30, 25, 255)
            elif d < 0.0125:
                px[x, y] = (95, 100, 108, 255)
            elif d < 0.0145:
                px[x, y] = (45, 48, 52, 255)
            elif (abs(p[0] - e[0]) < 0.0016 and n[1] - 0.03 < p[1] < e[1]
                  and p[2] < n[2] + 0.04):
                px[x, y] = (170, 175, 180, 230)
    return img


# ---------------------------------------------------------------------------
# Meshes (head space: +x up, +z out of the face, y sideways)
# ---------------------------------------------------------------------------
def _norm(v):
    m = math.sqrt(sum(c * c for c in v)) or 1
    return tuple(c / m for c in v)


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _sub(a, b):
    return tuple(a[i] - b[i] for i in range(3))


def _tri(mb, a, b, c):
    nrm = _norm(_cross(_sub(b, a), _sub(c, a)))
    mb.tri(a, b, c, (0, 0, 16, 16), nrm, ((0.5, 0.2), (0.8, 0.8), (0.2, 0.8)))


def vulcan_ears(body):
    """A pointed ear on each side: a leaf-shaped flap over the painted ear,
    standing a little proud of the head, rising up and back to a point."""
    ex, ey, ez = body.ear_local
    mb = MeshBuilder(16, 16)
    for s in (-1, 1):
        y0 = s * (abs(ey) + 0.003)
        # The outline, from the lobe round the front, over the tip and down
        # the back: a flat ring, fanned from its middle.
        outline = [(ex - 0.022, ez + 0.004), (ex - 0.006, ez + 0.012),
                   (ex + 0.012, ez + 0.006), (ex + 0.036, ez - 0.020),
                   (ex + 0.010, ez - 0.016), (ex - 0.012, ez - 0.012)]
        lean = lambda h: s * max(0.0, h - ex) * 0.18      # the tip splays out
        ring = [(h, y0 + lean(h), z) for h, z in outline]
        centre = (ex, y0, ez - 0.002)
        thick = s * 0.0030
        back = [(p[0], p[1] - thick, p[2]) for p in ring]
        cback = (centre[0], centre[1] - thick, centre[2])
        k = len(ring)
        for i in range(k):
            a, b = ring[i], ring[(i + 1) % k]
            c, d = back[i], back[(i + 1) % k]
            if s > 0:
                _tri(mb, centre, b, a)
                _tri(mb, cback, c, d)
            else:
                _tri(mb, centre, a, b)
                _tri(mb, cback, d, c)
            _tri(mb, a, b, d)
            _tri(mb, a, d, c)
    return mb


def antennae(body):
    """Two stalks from the top of the head, leaning out and forward, each with
    a rounded bulb at its tip."""
    top = body.head_local_top
    mb = MeshBuilder(16, 16)
    sides = 6
    for s in (-1, 1):
        base = (top - 0.010, s * 0.028, 0.020)
        tip = (top + 0.060, s * 0.045, 0.034)
        axis = _norm(_sub(tip, base))
        ref = (0, 0, 1) if abs(axis[2]) < 0.9 else (1, 0, 0)
        u = _norm(_cross(axis, ref))
        v = _cross(axis, u)

        def ring(centre, r):
            return [tuple(centre[i] + r * (math.cos(2 * math.pi * k / sides) * u[i]
                                           + math.sin(2 * math.pi * k / sides) * v[i])
                          for i in range(3)) for k in range(sides)]

        lo, hi = ring(base, 0.0042), ring(tip, 0.0030)
        for k in range(sides):
            k2 = (k + 1) % sides
            _tri(mb, lo[k], lo[k2], hi[k2])
            _tri(mb, lo[k], hi[k2], hi[k])
        # The bulb: two rings either side of its centre, capped.
        centre = tuple(tip[i] + axis[i] * 0.006 for i in range(3))
        below = ring(tuple(centre[i] - axis[i] * 0.004 for i in range(3)), 0.0065)
        above = ring(tuple(centre[i] + axis[i] * 0.004 for i in range(3)), 0.0065)
        bottom = tuple(centre[i] - axis[i] * 0.0085 for i in range(3))
        cap = tuple(centre[i] + axis[i] * 0.0085 for i in range(3))
        for k in range(sides):
            k2 = (k + 1) % sides
            _tri(mb, bottom, below[k2], below[k])
            _tri(mb, below[k], below[k2], above[k2])
            _tri(mb, below[k], above[k2], above[k])
            _tri(mb, above[k], above[k2], cap)
    return mb


def swatch(colour, path):
    """A 16x16 texture of one colour with a little shading, for a mesh."""
    img = Image.new("RGBA", (16, 16))
    px = img.load()
    for y in range(16):
        for x in range(16):
            k = 1.08 - 0.16 * (y / 15)
            px[x, y] = tuple(min(255, int(c * k)) for c in colour) + (255,)
    img.save(path, optimize=True)


def skin_tone(sex, tone):
    """The median face colour of one vanilla skin tone."""
    img = Image.open(os.path.join(PZ, "textures", "Body",
                                  BODY_TEX[sex].format(tone) + ".png")).convert("RGB")
    px = img.load()
    cols = sorted((px[x, y] for y in range(20, 60) for x in range(110, 140)),
                  key=lambda c: sum(c))
    return cols[len(cols) // 2]


# ---------------------------------------------------------------------------
# Clothing XMLs, the GUID table, the item scripts
# ---------------------------------------------------------------------------
def guid(stem):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, GUID_NAMESPACE + stem))


def write_xml(root, stem, male=None, female=None, bone="", textures=(), base=None):
    lines = ['<?xml version="1.0" encoding="utf-8"?>', "<clothingItem>",
             f"\t<m_MaleModel>{male or ''}</m_MaleModel>",
             f"\t<m_FemaleModel>{female or ''}</m_FemaleModel>",
             f"\t<m_GUID>{guid(stem)}</m_GUID>",
             "\t<m_Static>false</m_Static>",
             "\t<m_AllowRandomHue>false</m_AllowRandomHue>",
             "\t<m_AllowRandomTint>false</m_AllowRandomTint>",
             f"\t<m_AttachBone>{bone}</m_AttachBone>"]
    if base:
        lines.append(f"\t<m_BaseTextures>{base}</m_BaseTextures>")
    for t in textures:
        lines.append(f"\t<textureChoices>{t}</textureChoices>")
    lines.append("</clothingItem>")
    path = os.path.join(root, "media", "clothing", "clothingItems", stem + ".xml")
    with open(path, "w", encoding="utf-8", newline="\r\n") as fh:
        fh.write("\n".join(lines) + "\n")
    return f"media/clothing/clothingItems/{stem}.xml", guid(stem)


def merge_guid_table(root, rows):
    """Adds or replaces these rows in media/fileGuidTable.xml, keeping every
    other row. gen_uniform.py writes the same file; neither may drop the
    other's rows, or a regenerated uniform orphans a species' look."""
    import re
    path = os.path.join(root, "media", "fileGuidTable.xml")
    existing = []
    if os.path.isfile(path):
        src = open(path, encoding="utf-8").read()
        existing = re.findall(r"<path>(.*?)</path>\s*<guid>(.*?)</guid>", src, re.S)
    mine = {p for p, _ in rows}
    keep = [(p, g) for p, g in existing if p not in mine]
    table = ['<?xml version="1.0" encoding="utf-8"?>', "<fileGuidTable>"]
    for p, g in keep + list(rows):
        table += ["\t<files>", f"\t\t<path>{p}</path>", f"\t\t<guid>{g}</guid>", "\t</files>"]
    table.append("</fileGuidTable>")
    with open(path, "w", encoding="utf-8", newline="\r\n") as fh:
        fh.write("\n".join(table) + "\n")


# The item names the Lua and the script share. One per sex, as vanilla's
# stubble is (M_Hair_Stubble / F_Hair_Stubble): the two bodies' atlases
# differ, so one texture cannot serve both.
def look_items():
    items = [f"TrekLook_{kind}_{sex}" for kind in OVERLAYS for sex in ("M", "F")]
    return items + [f"TrekLook_{kind}" for kind in MESHES]


def main(root):
    tex_body = os.path.join(root, "media", "textures", "Body")
    tex_over = os.path.join(tex_body, "trek")
    tex_mesh = os.path.join(root, "media", "textures", "Clothes", "trek")
    model_dir = os.path.join(root, "media", "models_X", "Skinned", "Clothes")
    for d in (tex_body, tex_over, tex_mesh, model_dir,
              os.path.join(root, "media", "clothing", "clothingItems")):
        os.makedirs(d, exist_ok=True)

    made = skins(tex_body)
    print(f"  {len(made)} skins")

    rows = []
    rng = random.Random(4077)
    bodies = {sex: Body(sex) for sex in ("M", "F")}
    for sex, body in bodies.items():
        print(f"  {sex}: nose {tuple(round(c, 3) for c in body.nose)}, eyes "
              f"{[tuple(round(c, 3) for c in e) for e in body.eyes]}, ear (head space) "
              f"{tuple(round(c, 3) for c in body.ear_local)}")
        for kind in OVERLAYS:
            img = overlay(body, kind, rng)
            name = f"{kind}_{sex.lower()}"
            img.save(os.path.join(tex_over, name + ".png"), optimize=True)
            painted = sum(1 for p in img.get_flattened_data() if p[3] > 0)
            if painted < 6:
                raise SystemExit(f"{kind} ({sex}) painted {painted} texels -- its "
                                 f"region is empty, so the look would be invisible")
            rows.append(write_xml(root, f"TrekLook_{kind}_{sex}", base=f"body\\trek\\{name}"))

        for kind, build in (("vulcanears", vulcan_ears), ("antennae", antennae)):
            mb = build(body)
            stem = f"TREK_{kind}_{sex}"
            mb.emit(os.path.join(model_dir, stem + ".X"), stem, f"{kind}.png", frame_name=stem)
            for tone in range(1, 6):
                colour = skin_tone(sex, tone)
                if kind == "antennae":
                    base = SKINS["Andorian"]
                    k = sum(colour) / sum(skin_tone(sex, 1))
                    colour = tuple(int(c * k) for c in base)
                swatch(colour, os.path.join(tex_mesh, f"{kind}{tone}.png"))

    # A mesh look is one item for both sexes, each body with its own model:
    # a clothing item that names a model for one sex vanishes on the other.
    for kind in MESHES:
        rows.append(write_xml(
            root, f"TrekLook_{kind}",
            male=rf"media\models_X\Skinned\Clothes\TREK_{kind}_M.X",
            female=rf"media\models_X\Skinned\Clothes\TREK_{kind}_F.X",
            bone="Bip01_Head",
            textures=["clothes\\trek\\" + f"{kind}{t}" for t in range(1, 6)]))
    merge_guid_table(root, rows)
    print(f"  {len(rows)} look items, their XMLs and GUID rows")
    return bodies


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "TrekShuttle", "42"))
