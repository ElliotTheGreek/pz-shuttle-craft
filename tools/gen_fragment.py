"""The six holo fragments: one mesh, one texture, six numbered icons.

    python tools/gen_fragment.py TrekShuttle/42

Writes
    media/models_X/TREK_Fragment.x             a small hexagonal emitter
    media/textures/TREK_Fragment.png           bronze, with a lit face
    media/textures/Item_TREK_Fragment1..6.png  64x64, rendered from the mesh,
                                               each with its number on it
    design/art/fragment/fragment_sheet.png     the renders, and the icons at 64/32

LORE.md 1c: Tucker Gold left holo recordings, and a probe finds where. A
fragment is "an item, holographic, three hundred years old" -- small enough to
carry, losable like anything else, and **readable at a glance as one of six**,
because the whole of COMMS.md 6.3 is a player racing to get each one to
Shepard before it is lost. So every icon carries its number: the name in the
inventory says it too, but a hotbar and a loot panel are read by picture.

The icon is rendered from the same mesh and texture, the PADD's and the
bat'leth's route, so the two cannot drift apart.

Units are the character's (0.98 is about 1.8 m): a disc about 6 cm across
and 4 cm deep, 0.035 by 0.024 -- deep enough that the icon is not a sliver at 32px.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from meshbuild import MeshBuilder
from pngwrite import Image, draw_text, text_width
from preview_model import read_png_rgba, render
from gen_padd import icon_from, PREVIEW_BG

R, H = 0.035, 0.024
SIDES = 6
TEX = 128

TOP = (0, 0, 64, 64)
SIDE = (64, 0, 128, 32)
BOTTOM = (64, 32, 128, 64)

BRONZE = (150, 104, 58)
BRONZE_DARK = (92, 62, 34)
BRONZE_LIGHT = (196, 150, 92)
GLOW = (120, 230, 255)
GLOW_DIM = (40, 110, 150)


def paint():
    img = Image(TEX, TEX, BRONZE + (255,))
    x0, y0, x1, y1 = TOP
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    r = (x1 - x0) / 2
    for y in range(y0, y1):
        for x in range(x0, x1):
            d = math.hypot(x + 0.5 - cx, y + 0.5 - cy) / r
            if d > 0.92:
                c = BRONZE_DARK
            elif d > 0.80:
                c = BRONZE_LIGHT
            else:
                # The lit face: bright at the middle, a ring two thirds out,
                # and the faint banding of a projection that is still running.
                k = max(0.0, 1.0 - d * 1.1)
                ring = 0.55 if 0.55 < d < 0.62 else 0.0
                band = 0.12 if int((y - y0) / 3) % 2 == 0 else 0.0
                f = min(1.0, k + ring + band)
                c = tuple(int(GLOW_DIM[i] + (GLOW[i] - GLOW_DIM[i]) * f) for i in range(3))
            img.set(x, y, c + (255,))
    sx0, sy0, sx1, sy1 = SIDE
    img.rect(sx0, sy0, sx1, sy1, BRONZE + (255,))
    img.rect(sx0, sy0 + 4, sx1, sy0 + 8, BRONZE_LIGHT + (255,))
    img.rect(sx0, sy1 - 6, sx1, sy1, BRONZE_DARK + (255,))
    bx0, by0, bx1, by1 = BOTTOM
    img.rect(bx0, by0, bx1, by1, BRONZE_DARK + (255,))
    return img


def mesh():
    mb = MeshBuilder(TEX, TEX, up_axis="y")
    P = mb.place
    pts = [(R * math.cos(2 * math.pi * i / SIDES + math.pi / 6),
            R * math.sin(2 * math.pi * i / SIDES + math.pi / 6)) for i in range(SIDES)]

    def uv_top(x, y):
        return (0.5 + x / (2 * R), 0.5 - y / (2 * R))

    for i in range(SIDES):
        a, b = pts[i], pts[(i + 1) % SIDES]
        # The lit face, a fan from the centre, winding counter-clockwise
        # seen from above.
        mb.tri(P(0, 0, H), P(a[0], a[1], H), P(b[0], b[1], H), TOP, P(0, 0, 1),
               (uv_top(0, 0), uv_top(*a), uv_top(*b)))
        # The underside, the other way round.
        mb.tri(P(0, 0, 0), P(b[0], b[1], 0), P(a[0], a[1], 0), BOTTOM, P(0, 0, -1))
        # The rim.
        mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        n = math.hypot(mx, my)
        mb.quad(P(a[0], a[1], 0), P(b[0], b[1], 0), P(b[0], b[1], H), P(a[0], a[1], H),
                SIDE, P(mx / n, my / n, 0))
    return mb


def numbered(base_path, out_path, n):
    """The icon with its number in a dark disc at the bottom right."""
    w, h, px = read_png_rgba(base_path)
    img = Image(w, h, (0, 0, 0, 0))
    for y in range(h):
        for x in range(w):
            j = (y * w + x) * 4
            img.set(x, y, tuple(px[j:j + 4]))
    cx, cy, rad = w - 18, h - 18, 17
    for y in range(h):
        for x in range(w):
            d = math.hypot(x + 0.5 - cx, y + 0.5 - cy)
            if d <= rad:
                edge = d > rad - 2
                img.set(x, y, (255, 204, 102, 255) if edge else (20, 18, 26, 255))
    s = str(n)
    scale = 4
    tw = text_width(s, scale)
    draw_text(img, s, int(cx - tw / 2) + 1, cy - 13, (255, 255, 255, 255), scale)
    img.save(out_path)


def build(root, art):
    media = os.path.join(root, "media")
    os.makedirs(art, exist_ok=True)
    tex_path = os.path.join(media, "textures", "TREK_Fragment.png")
    paint().save(tex_path)
    mb = mesh()
    x_path = os.path.join(media, "models_X", "TREK_Fragment.x")
    nv, nf = mb.emit(x_path, "TREK_Fragment", "TREK_Fragment.png")
    print(f"TREK_Fragment: {nv} vertices, {nf} faces, {2 * R} across, {H} deep")

    render_path = os.path.join(art, "_fragment_iso.png")
    render(x_path, tex_path, render_path, size=256, yaw_deg=-35)
    base = os.path.join(art, "_fragment_icon.png")
    covered = icon_from(render_path, base)
    print(f"icon: {covered} pixels covered")
    icons = []
    for n in range(1, 7):
        out = os.path.join(media, "textures", f"Item_TREK_Fragment{n}.png")
        numbered(base, out, n)
        icons.append(out)

    # The sheet: the render, then all six at 64 and at 32 on the inventory's grey.
    sheet = Image(256 + 6 * 72 + 20, 256, PREVIEW_BG + (255,))
    w, h, px = read_png_rgba(render_path)
    for y in range(h):
        for x in range(w):
            j = (y * w + x) * 4
            sheet.set(x, y, tuple(px[j:j + 3]) + (255,))
    panel = (39, 39, 39)
    for k, p in enumerate(icons):
        iw, ih, ipx = read_png_rgba(p)
        for size, oy in ((64, 40), (32, 140)):
            ox = 266 + k * 72
            for y in range(size):
                for x in range(size):
                    j = ((y * ih // size) * iw + (x * iw // size)) * 4
                    r, g, b, a = ipx[j:j + 4]
                    f = a / 255
                    sheet.set(ox + x, oy + y, (int(panel[0] * (1 - f) + r * f),
                                               int(panel[1] * (1 - f) + g * f),
                                               int(panel[2] * (1 - f) + b * f), 255))
    draw_text(sheet, "64", 266, 20, (200, 200, 210, 255))
    draw_text(sheet, "32", 266, 120, (200, 200, 210, 255))
    for p in (render_path, base):
        os.remove(p)
    out = os.path.join(art, "fragment_sheet.png")
    sheet.save(out)
    print("sheet ->", out)


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else os.path.join("TrekShuttle", "42")
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    build(root, os.path.join(here, "design", "art", "fragment"))
