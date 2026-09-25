"""Renders each species' head as the game would dress it, for looking at.

    python tools/preview_species.py TrekShuttle/42 [M|F]

Writes design/art/species/species_<sex>.png: every species at two angles,
front and three-quarter, on the bind-pose head -- the recoloured skin or a
vanilla tone, its overlay laid on top the way a body visual is, and its
meshes moved from head space into the body's frame by the Bip01_Head bind
matrix, which is where m_AttachBone puts them in game.

This is how the looks are judged before anybody starts the game: a spot
pattern that lands on the scalp instead of the temple, an ear that sits
inside the head, an antenna that points backwards -- all of it shows here.
"""
import math
import os
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xskin  # noqa: E402
from preview_model import parse_x  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PZ = r"C:\Program Files (x86)\Steam\steamapps\common\ProjectZomboid\media"

LOOKS = [
    ("Human", None, None, []),
    ("Vulcan", None, None, ["vulcanears"]),
    ("Klingon", None, "klingon", []),
    ("Andorian", "Andorian", None, ["antennae"]),
    ("Betazoid", None, "betazoid", []),
    ("Trill", None, "trill", []),
    ("Bajoran", None, "bajoran", []),
    ("Talaxian", None, "talaxian", []),
    ("Orion", "Orion", None, []),
    ("Android", "Android", None, []),
    ("Ex-Borg", None, "exborg", []),
]
TONE = 2


def head_mesh(sex):
    nodes = xskin.parse(os.path.join(PZ, "models_X", "Skinned",
                                     "MaleBody.x" if sex == "M" else "FemaleBody.x"))
    sk = xskin.Skeleton(nodes)
    mesh = xskin.meshes(nodes)[0]
    world = sk.world()
    pos = mesh.skin(world)
    dom = mesh.dominant_bones()
    keep = {"Bip01_Head", "Bip01_Neck"}
    tris = [(a, b, c) for a, b, c in mesh.faces
            if dom[a] in keep and dom[b] in keep and dom[c] in keep]
    return pos, mesh.uvs, tris, world["Bip01_Head"]


def composite(root, sex, skin, over):
    base = (os.path.join(root, "media", "textures", "Body", f"TREK_{skin}_{sex}{TONE}.png")
            if skin else os.path.join(PZ, "textures", "Body",
                                      ("MaleBody0" if sex == "M" else "FemaleBody0") + f"{TONE}.png"))
    img = Image.open(base).convert("RGBA")
    if over:
        img.alpha_composite(Image.open(os.path.join(root, "media", "textures", "Body", "trek",
                                                    f"{over}_{sex.lower()}.png")).convert("RGBA"))
    return img


def draw(tris, size, yaw):
    """tris: list of (p0, p1, p2, colour-function(l1, l2, l3))."""
    img = Image.new("RGB", (size, size), (39, 39, 39))
    px = img.load()
    zb = [[1e9] * size for _ in range(size)]
    cy, sy = math.cos(yaw), math.sin(yaw)

    def rot(p):
        x, y, z = p
        return (x * cy - z * sy, y, x * sy + z * cy)

    allp = [rot(p) for t in tris for p in t[:3]]
    xs = [p[0] for p in allp]
    ys = [p[1] for p in allp]
    span = max(max(xs) - min(xs), max(ys) - min(ys))
    sc = size * 0.9 / span
    cx, cyy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
    light = (0.35, 0.45, -0.82)
    for t in tris:
        a, b, c = (rot(p) for p in t[:3])
        P = [(size / 2 + (p[0] - cx) * sc, size / 2 - (p[1] - cyy) * sc, p[2]) for p in (a, b, c)]
        e1 = [b[i] - a[i] for i in range(3)]
        e2 = [c[i] - a[i] for i in range(3)]
        n = (e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0])
        m = math.sqrt(sum(v * v for v in n)) or 1
        shade = 0.55 + 0.45 * abs(sum(n[i] / m * light[i] for i in range(3)))
        d = (P[1][1] - P[2][1]) * (P[0][0] - P[2][0]) + (P[2][0] - P[1][0]) * (P[0][1] - P[2][1])
        if abs(d) < 1e-9:
            continue
        for y in range(max(0, int(min(p[1] for p in P))), min(size - 1, int(max(p[1] for p in P)) + 1) + 1):
            for x in range(max(0, int(min(p[0] for p in P))), min(size - 1, int(max(p[0] for p in P)) + 1) + 1):
                l1 = ((P[1][1] - P[2][1]) * (x - P[2][0]) + (P[2][0] - P[1][0]) * (y - P[2][1])) / d
                l2 = ((P[2][1] - P[0][1]) * (x - P[2][0]) + (P[0][0] - P[2][0]) * (y - P[2][1])) / d
                l3 = 1 - l1 - l2
                if min(l1, l2, l3) < -0.01:
                    continue
                z = l1 * P[0][2] + l2 * P[1][2] + l3 * P[2][2]
                if z >= zb[y][x]:
                    continue
                zb[y][x] = z
                col = t[3](l1, l2, l3)
                px[x, y] = tuple(int(v * shade) for v in col[:3])
    return img


def render(root, sex, size=220):
    pos, uvs, tris, head_m = head_mesh(sex)
    cells = []
    for name, skin, over, meshes in LOOKS:
        tex = composite(root, sex, skin, over)
        tw, th = tex.size
        tp = tex.load()
        items = []
        for a, b, c in tris:
            ua, ub, uc = uvs[a], uvs[b], uvs[c]

            def col(l1, l2, l3, ua=ua, ub=ub, uc=uc):
                u = l1 * ua[0] + l2 * ub[0] + l3 * uc[0]
                v = l1 * ua[1] + l2 * ub[1] + l3 * uc[1]
                return tp[int(u * tw) % tw, int(v * th) % th]
            items.append((pos[a], pos[b], pos[c], col))
        for kind in meshes:
            verts, faces, _ = parse_x(os.path.join(root, "media", "models_X", "Skinned", "Clothes",
                                                   f"TREK_{kind}_{sex}.X"))
            sw = Image.open(os.path.join(root, "media", "textures", "Clothes", "trek",
                                         f"{kind}{TONE}.png")).convert("RGB")
            colour = sw.getpixel((8, 8))
            wv = [xskin.transform(v, head_m) for v in verts]
            for f in faces:
                items.append((wv[f[0]], wv[f[1]], wv[f[2]], lambda *_, c=colour: c))
        row = Image.new("RGB", (size * 2, size + 18), (39, 39, 39))
        row.paste(draw(items, size, 0.0), (0, 0))
        row.paste(draw(items, size, math.radians(-50)), (size, 0))
        cells.append((name, row))
    cols = 4
    rows = (len(cells) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * size * 2, rows * (size + 18)), (39, 39, 39))
    for i, (_, row) in enumerate(cells):
        sheet.paste(row, ((i % cols) * size * 2, (i // cols) * (size + 18)))
    out_dir = os.path.join(ROOT, "design", "art", "species")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, f"species_{sex}.png")
    sheet.save(out)
    print("->", out, "order:", ", ".join(n for n, _ in cells))


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "TrekShuttle", "42")
    for sex in (sys.argv[2:] or ["M", "F"]):
        render(root, sex)
