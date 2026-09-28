"""Boarding clearance's two items (ACCESS.md): a pattern enhancer and a
nanoprobe sample. One mesh, one texture and one icon each.

    python tools/gen_access.py TrekShuttle/42

Writes
    media/models_X/TREK_PatternEnhancer.x         a standing rod: foot, shaft, lit band, cap
    media/models_X/TREK_NanoprobeSample.x         a sealed vial
    media/textures/TREK_PatternEnhancer.png
    media/textures/TREK_NanoprobeSample.png
    media/textures/Item_TREK_PatternEnhancer.png  64x64, rendered from the mesh
    media/textures/Item_TREK_NanoprobeSample.png  64x64, rendered from the mesh
    design/art/access/access_sheet.png            the renders, and the icons at 64/32

**A pattern enhancer stands up**, because three of them standing in a
triangle round the player is the whole of the lock (ACCESS.md 3.8), and a rod
lying on its side reads as a pipe. It is about a metre tall -- the canon ones
are -- at the character's units (0.98 is about 1.8 m).

**The icon is the rod tilted and thickened.** Upright in a square frame a rod
is a sliver (DEV_GUIDE: *A weapon icon is a thin sliver next to the rest of
the set*), so the icon is rendered from a copy of the mesh leaned over to the
diagonal and fattened, from the same texture, so the two cannot drift apart.

The vial is small and green-grey: a Borg's nanoprobes in suspension, with the
dark cap vanilla's own sample jars use.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from meshbuild import MeshBuilder
from pngwrite import Image, draw_text
from preview_model import read_png_rgba, render
from gen_padd import icon_from, PREVIEW_BG

TEX = 64
# Regions of each 64x64 sheet.
METAL = (0, 0, 32, 32)
DARK = (32, 0, 64, 32)
GLOW = (0, 32, 32, 64)
TOPR = (32, 32, 64, 64)

SILVER = (168, 174, 186)
SILVER_LIGHT = (214, 220, 230)
GUNMETAL = (58, 62, 72)
GLOW_C = (110, 200, 255)
GLOW_CORE = (225, 245, 255)

GLASS = (86, 128, 96)
GLASS_LIGHT = (150, 196, 160)
PROBE = (40, 58, 44)


def paint_enhancer():
    img = Image(TEX, TEX, SILVER + (255,))
    x0, y0, x1, y1 = METAL
    for y in range(y0, y1):
        for x in range(x0, x1):
            # A brushed finish: a lighter stripe down one face.
            c = SILVER_LIGHT if 10 <= x - x0 <= 14 else SILVER
            img.set(x, y, c + (255,))
    img.rect(*DARK, GUNMETAL + (255,))
    x0, y0, x1, y1 = GLOW
    for y in range(y0, y1):
        for x in range(x0, x1):
            k = 1.0 - abs((y - y0) - 16) / 16.0
            c = tuple(int(GLOW_C[i] + (GLOW_CORE[i] - GLOW_C[i]) * k) for i in range(3))
            img.set(x, y, c + (255,))
    x0, y0, x1, y1 = TOPR
    for y in range(y0, y1):
        for x in range(x0, x1):
            d = math.hypot(x + 0.5 - (x0 + 16), y + 0.5 - (y0 + 16)) / 16
            c = GLOW_CORE if d < 0.5 else GUNMETAL
            img.set(x, y, c + (255,))
    return img


def paint_vial():
    img = Image(TEX, TEX, GLASS + (255,))
    x0, y0, x1, y1 = METAL
    for y in range(y0, y1):
        for x in range(x0, x1):
            # Suspended probes: a dark speckle in green glass, a highlight.
            speck = ((x * 7 + y * 13) % 11) == 0
            c = PROBE if speck else (GLASS_LIGHT if 4 <= x - x0 <= 7 else GLASS)
            img.set(x, y, c + (255,))
    img.rect(*DARK, GUNMETAL + (255,))
    img.rect(*GLOW, GLASS + (255,))
    img.rect(*TOPR, GUNMETAL + (255,))
    return img


def prism(mb, sides, r, z0, z1, side, top, bottom, tf):
    """A vertical prism from height z0 to z1, every point passed through tf."""
    P = lambda a, b, c: mb.place(*tf(a, b, c))
    pts = [(r * math.cos(2 * math.pi * i / sides), r * math.sin(2 * math.pi * i / sides))
           for i in range(sides)]
    for i in range(sides):
        a, b = pts[i], pts[(i + 1) % sides]
        mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        n = math.hypot(mx, my)
        mb.quad(P(a[0], a[1], z0), P(b[0], b[1], z0), P(b[0], b[1], z1), P(a[0], a[1], z1),
                side, P(mx / n, my / n, 0))
        if top:
            mb.tri(P(0, 0, z1), P(a[0], a[1], z1), P(b[0], b[1], z1), top, P(0, 0, 1))
        if bottom:
            mb.tri(P(0, 0, z0), P(b[0], b[1], z0), P(a[0], a[1], z0), bottom, P(0, 0, -1))


def upright(a, b, c):
    return a, b, c


def leaned(fat):
    """The icon's copy: thickened, and leaned 45 degrees over to the east."""
    k = math.radians(45)

    def tf(a, b, c):
        a, b = a * fat, b * fat
        return a * math.cos(k) + c * math.sin(k), b, -a * math.sin(k) + c * math.cos(k)
    return tf


def enhancer_mesh(tf):
    mb = MeshBuilder(TEX, TEX, up_axis="y")
    prism(mb, 6, 0.045, 0.0, 0.03, DARK, DARK, DARK, tf)          # the foot
    prism(mb, 6, 0.022, 0.03, 0.40, METAL, None, None, tf)        # the shaft
    prism(mb, 6, 0.028, 0.40, 0.44, GLOW, DARK, DARK, tf)         # the lit band
    prism(mb, 6, 0.022, 0.44, 0.47, METAL, None, None, tf)
    prism(mb, 6, 0.018, 0.47, 0.50, DARK, TOPR, None, tf)         # the cap
    return mb


def vial_mesh(tf):
    mb = MeshBuilder(TEX, TEX, up_axis="y")
    prism(mb, 8, 0.018, 0.0, 0.06, METAL, None, DARK, tf)
    prism(mb, 8, 0.021, 0.06, 0.078, DARK, TOPR, DARK, tf)
    return mb


def build_one(media, art, name, paint, mesh, icon_tf):
    tex_path = os.path.join(media, "textures", f"TREK_{name}.png")
    paint().save(tex_path)
    x_path = os.path.join(media, "models_X", f"TREK_{name}.x")
    nv, nf = mesh(upright).emit(x_path, f"TREK_{name}", f"TREK_{name}.png")
    print(f"TREK_{name}: {nv} vertices, {nf} faces")
    view = os.path.join(art, f"_{name}_view.png")
    render(x_path, tex_path, view, size=256, yaw_deg=-35)
    icon_x = os.path.join(art, f"_{name}_icon.x")
    mesh(icon_tf).emit(icon_x, f"TREK_{name}", f"TREK_{name}.png")
    icon_render = os.path.join(art, f"_{name}_iconview.png")
    render(icon_x, tex_path, icon_render, size=256, yaw_deg=-35)
    icon = os.path.join(media, "textures", f"Item_TREK_{name}.png")
    covered = icon_from(icon_render, icon)
    print(f"  icon: {covered} pixels covered")
    os.remove(icon_x)
    os.remove(icon_render)
    return view, icon


def build(root, art):
    media = os.path.join(root, "media")
    os.makedirs(art, exist_ok=True)
    made = [
        build_one(media, art, "PatternEnhancer", paint_enhancer, enhancer_mesh, leaned(2.4)),
        build_one(media, art, "NanoprobeSample", paint_vial, vial_mesh, upright),
    ]
    # The sheet: each render, then its icon at 64 and 32 on the inventory's grey.
    sheet = Image(2 * (256 + 120), 256, PREVIEW_BG + (255,))
    panel = (39, 39, 39)
    for k, (view, icon) in enumerate(made):
        ox0 = k * (256 + 120)
        w, h, px = read_png_rgba(view)
        for y in range(h):
            for x in range(w):
                j = (y * w + x) * 4
                sheet.set(ox0 + x, y, tuple(px[j:j + 3]) + (255,))
        iw, ih, ipx = read_png_rgba(icon)
        for size, oy in ((64, 40), (32, 140)):
            ox = ox0 + 266
            for y in range(size):
                for x in range(size):
                    j = ((y * ih // size) * iw + (x * iw // size)) * 4
                    r, g, b, a = ipx[j:j + 4]
                    f = a / 255
                    sheet.set(ox + x, oy + y, (int(panel[0] * (1 - f) + r * f),
                                               int(panel[1] * (1 - f) + g * f),
                                               int(panel[2] * (1 - f) + b * f), 255))
        draw_text(sheet, "64", ox0 + 266, 20, (200, 200, 210, 255))
        draw_text(sheet, "32", ox0 + 266, 120, (200, 200, 210, 255))
        os.remove(view)
    out = os.path.join(art, "access_sheet.png")
    sheet.save(out)
    print("sheet ->", out)


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else os.path.join("TrekShuttle", "42")
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    build(root, os.path.join(here, "design", "art", "access"))
