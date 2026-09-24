"""The PADD: its mesh, its texture, its icon and the render it was judged on.

    python tools/gen_padd.py TrekShuttle/42

Writes
    media/models_X/TREK_PADD.x            a slim slab, screen up
    media/textures/TREK_PADD.png          the LCARS screen and the case
    media/textures/Item_TREK_PADD.png     64x64, rendered from the mesh
    design/art/padd/padd_sheet.png        the renders, and the icon at 64/32

A box with a picture on one face, which is the right shape for a script to
describe (PADD.md section 6). The icon is rendered from the same mesh and
texture, the bat'leth's route, so the two cannot drift apart.

**The mesh lies flat, screen up**, because that is how a world item sits on
the floor. How it sits in the hand is the `Bip01_Prop2` attachment in the
model script, and those six numbers can only honestly be chosen by looking at
it in a fist -- the same open question the blades had (ROADMAP.md).

Units are the character's: a PADD is about 16 x 24 cm and a character 0.98
units is about 1.8 m, so 0.087 x 0.13 x 0.008.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from meshbuild import MeshBuilder
from pngwrite import Image, draw_text
from preview_model import read_png_rgba, render

W, L, H = 0.087, 0.13, 0.008        # east, north, height
TEX = 128

# Texture regions (x0, y0, x1, y1) in texels.
SCREEN = (0, 0, 84, 128)
CASE = (88, 0, 128, 40)
BACK = (88, 44, 128, 128)

BLACK = (8, 8, 14)
BEZEL = (46, 48, 56)
CASE_GREY = (92, 96, 108)
CASE_DARK = (58, 60, 70)
ORANGE = (255, 153, 0)
LILAC = (204, 153, 204)
BLUE = (153, 204, 255)
GOLD = (255, 204, 102)
PEACH = (255, 170, 144)
PREVIEW_BG = (28, 30, 36)


def paint():
    img = Image(TEX, TEX, CASE_GREY + (255,))
    x0, y0, x1, y1 = SCREEN
    img.rect(x0, y0, x1, y1, BEZEL + (255,))
    sx0, sy0, sx1, sy1 = x0 + 5, y0 + 6, x1 - 5, y1 - 10
    img.rect(sx0, sy0, sx1, sy1, BLACK + (255,))

    # The LCARS frame: an elbow top left, a sidebar, a bar along the bottom.
    img.rect(sx0 + 2, sy0 + 2, sx0 + 16, sy0 + 34, ORANGE + (255,))
    img.rect(sx0 + 16, sy0 + 2, sx1 - 2, sy0 + 9, ORANGE + (255,))
    img.rect(sx0 + 2, sy0 + 37, sx0 + 16, sy0 + 62, LILAC + (255,))
    img.rect(sx0 + 2, sy0 + 65, sx0 + 16, sy1 - 14, GOLD + (255,))
    img.rect(sx0 + 2, sy1 - 11, sx1 - 2, sy1 - 4, LILAC + (255,))

    # "Text": rows of short bars, the way a page reads from across a room.
    y = sy0 + 16
    widths = (40, 34, 44, 28, 38, 42, 20, 36, 44, 30, 40, 24, 38, 33)
    for i, w in enumerate(widths):
        colour = BLUE if i % 5 else PEACH
        img.rect(sx0 + 21, y, min(sx1 - 3, sx0 + 21 + w), y + 2, colour + (255,))
        y += 6
        if y > sy1 - 18:
            break

    # The hardware button below the screen.
    img.rect((x0 + x1) // 2 - 6, y1 - 7, (x0 + x1) // 2 + 6, y1 - 4, CASE_DARK + (255,))

    cx0, cy0, cx1, cy1 = CASE
    img.rect(cx0, cy0, cx1, cy1, CASE_GREY + (255,))
    for yy in range(cy0, cy1, 6):
        img.rect(cx0, yy, cx1, yy + 1, CASE_DARK + (255,))
    bx0, by0, bx1, by1 = BACK
    img.rect(bx0, by0, bx1, by1, CASE_DARK + (255,))
    img.rect(bx0 + 12, by0 + 30, bx1 - 12, by0 + 50, CASE_GREY + (255,))
    return img


def mesh():
    mb = MeshBuilder(TEX, TEX, up_axis="y")
    P = mb.place
    hw, hl = W / 2, L / 2
    # Screen, face up. The texture's top edge is the far (north) end.
    mb.quad(P(-hw, -hl, H), P(hw, -hl, H), P(hw, hl, H), P(-hw, hl, H),
            SCREEN, P(0, 0, 1))
    # Back, face down.
    mb.quad(P(-hw, hl, 0), P(hw, hl, 0), P(hw, -hl, 0), P(-hw, -hl, 0),
            BACK, P(0, 0, -1))
    # Four thin edges.
    mb.quad(P(-hw, -hl, 0), P(hw, -hl, 0), P(hw, -hl, H), P(-hw, -hl, H),
            CASE, P(0, -1, 0))
    mb.quad(P(hw, -hl, 0), P(hw, hl, 0), P(hw, hl, H), P(hw, -hl, H),
            CASE, P(1, 0, 0))
    mb.quad(P(hw, hl, 0), P(-hw, hl, 0), P(-hw, hl, H), P(hw, hl, H),
            CASE, P(0, 1, 0))
    mb.quad(P(-hw, hl, 0), P(-hw, -hl, 0), P(-hw, -hl, H), P(-hw, hl, H),
            CASE, P(-1, 0, 0))
    return mb


def icon_from(render_path, out_path, size=64):
    """The render, keyed by exact match on the flat preview background, then
    shrunk with alpha-weighted averaging. DEV_GUIDE: the previewer does not
    antialias, so the key is exact and nothing of the case is eaten."""
    w, h, px = read_png_rgba(render_path)
    # Crop to the object first, as a square with a small margin: the render
    # auto-fits the model's bounding box *before* the camera tilt, so a flat
    # slab seen from above fills a quarter of it, and an icon made from the
    # whole frame is a small tablet in a big empty square.
    xs, ys = [], []
    for y in range(h):
        for x in range(w):
            i = (y * w + x) * 4
            if tuple(px[i:i + 3]) != PREVIEW_BG:
                xs.append(x)
                ys.append(y)
    side = max(max(xs) - min(xs), max(ys) - min(ys)) + 1
    side = int(side * 1.06) + 2
    cx, cy = (max(xs) + min(xs)) // 2, (max(ys) + min(ys)) // 2
    left, top = cx - side // 2, cy - side // 2
    out = Image(size, size, (0, 0, 0, 0))
    scale = side / size
    for oy in range(size):
        for ox in range(size):
            r = g = b = a = 0
            n = 0
            for sy in range(top + int(oy * scale), top + int((oy + 1) * scale)):
                for sx in range(left + int(ox * scale), left + int((ox + 1) * scale)):
                    n += 1
                    if not (0 <= sx < w and 0 <= sy < h):
                        continue
                    i = (sy * w + sx) * 4
                    c = tuple(px[i:i + 3])
                    if c == PREVIEW_BG:
                        continue
                    r += c[0]
                    g += c[1]
                    b += c[2]
                    a += 1
            if a and n:
                out.set(ox, oy, (r // a, g // a, b // a, 255 * a // n))
    covered = sum(1 for y in range(size) for x in range(size) if out.get(x, y)[3] > 0)
    if covered < size * size // 5:
        raise SystemExit(f"icon: only {covered} of {size * size} pixels came out; "
                         f"the render or the key is wrong")
    out.save(out_path)
    return covered


def build(root, art):
    media = os.path.join(root, "media")
    os.makedirs(art, exist_ok=True)
    tex_path = os.path.join(media, "textures", "TREK_PADD.png")
    paint().save(tex_path)
    mb = mesh()
    x_path = os.path.join(media, "models_X", "TREK_PADD.x")
    nv, nf = mb.emit(x_path, "TREK_PADD", "TREK_PADD.png")
    print(f"TREK_PADD: {nv} vertices, {nf} faces, {W} x {L} x {H}")

    renders = []
    for name, yaw in (("iso", -35), ("side", 60)):
        p = os.path.join(art, f"_padd_{name}.png")
        render(x_path, tex_path, p, size=256, yaw_deg=yaw)
        renders.append(p)
    icon_path = os.path.join(media, "textures", "Item_TREK_PADD.png")
    covered = icon_from(renders[0], icon_path)
    print(f"icon: {covered} pixels covered")

    sheet = Image(256 * 2 + 64 + 32 + 40, 256, PREVIEW_BG + (255,))
    for i, p in enumerate(renders):
        w, h, px = read_png_rgba(p)
        for y in range(h):
            for x in range(w):
                j = (y * w + x) * 4
                sheet.set(i * 256 + x, y, tuple(px[j:j + 3]) + (255,))
        os.remove(p)
    iw, ih, ipx = read_png_rgba(icon_path)
    panel = (39, 39, 39)
    for size, ox in ((64, 520), (32, 600)):
        for y in range(size):
            for x in range(size):
                sxp, syp = x * iw // size, y * ih // size
                j = (syp * iw + sxp) * 4
                r, g, b, a = ipx[j:j + 4]
                f = a / 255
                sheet.set(ox + x, 40 + y, (int(panel[0] * (1 - f) + r * f),
                                           int(panel[1] * (1 - f) + g * f),
                                           int(panel[2] * (1 - f) + b * f), 255))
    draw_text(sheet, "64", 520, 20, (200, 200, 210, 255))
    draw_text(sheet, "32", 600, 20, (200, 200, 210, 255))
    out = os.path.join(art, "padd_sheet.png")
    sheet.save(out)
    print("sheet ->", out)


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else os.path.join("TrekShuttle", "42")
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    build(root, os.path.join(here, "design", "art", "padd"))
