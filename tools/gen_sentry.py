"""The perimeter phaser sentry: mesh, texture, icon, and the sheet it was judged on.

    python tools/gen_sentry.py TrekShuttle/42

Writes
    media/models_X/TREK_Sentry.x            a foot, a mast, a head with an emitter band
    media/textures/TREK_Sentry.png          the metal, the gold trim, the emitter
    media/textures/Item_TREK_Sentry.png     64x64, rendered from the mesh
    design/art/sentry/sentry_sheet.png      the renders, and the icon at 64/32

It stands on the ground as a world item, so the mesh's origin is its foot and
it is Y-up (the PADD's convention, `up_axis="y"`). The emitter goes all the
way round the head because it fires in every direction, and it is the one
colour on it that still reads at the size the game draws a knee-high object:
a phaser's orange.

Units are the character's (0.98 is about 1.8 m): 0.26 tall is about 48 cm,
a little larger than a real one would be for the same reason the shoulder
lamp is -- at game zoom a true-size one is a few pixels.
"""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np

from meshbuild import MeshBuilder
from pngwrite import Image, draw_text
from preview_model import read_png_rgba, render

TEX = 64
SIDES = 8

# (radius at the bottom, radius at the top, bottom, top), in model units.
FOOT = (0.075, 0.068, 0.000, 0.016)
MAST = (0.020, 0.018, 0.016, 0.150)
COLLAR = (0.030, 0.042, 0.150, 0.170)
EMITTER = (0.042, 0.042, 0.170, 0.205)
HEAD = (0.042, 0.030, 0.205, 0.235)
CROWN = (0.030, 0.000, 0.235, 0.260)

# Texture regions (x0, y0, x1, y1).
METAL = (0, 0, 32, 16)
DARK = (32, 0, 64, 16)
GOLD = (0, 16, 32, 24)
EMIT = (0, 24, 64, 40)
CAP = (32, 16, 64, 24)
TOPCAP = (0, 40, 32, 64)

GREY = (150, 154, 164)
GREY_DARK = (70, 74, 84)
GOLD_C = (230, 190, 90)
EMIT_EDGE = (255, 110, 30)
EMIT_MID = (255, 170, 70)
EMIT_HOT = (255, 235, 200)
PREVIEW_BG = (28, 30, 36)


def paint():
    img = Image(TEX, TEX, GREY + (255,))
    img.rect(*METAL, GREY + (255,))
    x0, y0, x1, y1 = METAL
    for x in range(x0, x1, 8):
        img.rect(x, y0, x + 1, y1, GREY_DARK + (255,))
    img.rect(*DARK, GREY_DARK + (255,))
    img.rect(*GOLD, GOLD_C + (255,))
    img.rect(*CAP, GREY_DARK + (255,))
    img.rect(*TOPCAP, GREY + (255,))
    # The emitter: hot in the middle of the band, orange at its edges -- a
    # line of light, which is what reads at 20 pixels.
    ex0, ey0, ex1, ey1 = EMIT
    mid = (ey0 + ey1) / 2
    for y in range(ey0, ey1):
        d = abs(y + 0.5 - mid) / ((ey1 - ey0) / 2)
        c = EMIT_HOT if d < 0.25 else EMIT_MID if d < 0.6 else EMIT_EDGE
        img.rect(ex0, y, ex1, y + 1, c + (255,))
    return img


def inset(region):
    """A region pulled in by a texel: the sampler reads past a triangle's
    edge, and a cap next to the emitter came out speckled orange."""
    x0, y0, x1, y1 = region
    return (x0 + 1, y0 + 1, x1 - 1, y1 - 1)


def mesh():
    mb = MeshBuilder(TEX, TEX, up_axis="y")
    P = mb.place           # (east, north, height)

    def quad(p0, p1, p2, p3, region, normal):
        # Winding decided in the (east, north, height) frame before place()
        # swaps to Y-up, the lamp's rule: (p1 - p0) x (p2 - p0) points out.
        a, b_, c = (np.array(p) for p in (p0, p1, p2))
        if np.dot(np.cross(b_ - a, c - a), normal) < 0:
            p0, p1, p2, p3 = p1, p0, p3, p2
        mb.quad(P(*p0), P(*p1), P(*p2), P(*p3), inset(region), P(*normal))

    def ring(r, z, i):
        a = 2 * math.pi * (i + 0.5) / SIDES
        return (r * math.cos(a), r * math.sin(a), z)

    def prism(spec, side, top=None, bottom=None):
        r0, r1, z0, z1 = spec
        for i in range(SIDES):
            a0, a1 = ring(r0, z0, i), ring(r0, z0, i + 1)
            b0, b1 = ring(r1, z1, i), ring(r1, z1, i + 1)
            if r1 == 0:
                b0 = b1 = (0.0, 0.0, z1)
            mid = 2 * math.pi * (i + 1) / SIDES
            n = (math.cos(mid) * (z1 - z0), math.sin(mid) * (z1 - z0), r0 - r1)
            quad(a0, a1, b1, b0, side, n)
        for cap, z, r, up in ((top, z1, r1, 1), (bottom, z0, r0, -1)):
            if cap is None or r == 0:
                continue
            for i in range(SIDES):
                p0, p1 = ring(r, z, i), ring(r, z, i + 1)
                quad((0.0, 0.0, z), p0, p1, (0.0, 0.0, z), cap, (0, 0, up))

    prism(FOOT, DARK, top=CAP, bottom=CAP)
    prism(MAST, METAL)
    prism(COLLAR, GOLD, bottom=CAP)
    prism(EMITTER, EMIT)
    prism(HEAD, METAL)
    prism(CROWN, GOLD)
    return mb


def build(root, art):
    from gen_padd import icon_from
    media = os.path.join(root, "media")
    os.makedirs(art, exist_ok=True)
    tex_path = os.path.join(media, "textures", "TREK_Sentry.png")
    paint().save(tex_path)
    x_path = os.path.join(media, "models_X", "TREK_Sentry.x")
    nv, nf = mesh().emit(x_path, "TREK_Sentry", "TREK_Sentry.png")
    print(f"TREK_Sentry: {nv} vertices, {nf} faces, {2 * FOOT[0]:.3f} across, {CROWN[3]:.3f} tall")

    renders = []
    for name, yaw in (("iso", 145), ("side", 90)):
        p = os.path.join(art, f"_sentry_{name}.png")
        render(x_path, tex_path, p, size=256, yaw_deg=yaw)
        renders.append(p)
    icon_path = os.path.join(media, "textures", "Item_TREK_Sentry.png")
    covered = icon_from(renders[0], icon_path, 64)
    print(f"icon    {icon_path}: {covered} of 4096 pixels covered")

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
                j = ((y * ih // size) * iw + x * iw // size) * 4
                r, g, b_, a = ipx[j:j + 4]
                f = a / 255
                sheet.set(ox + x, 40 + y, (int(panel[0] * (1 - f) + r * f),
                                           int(panel[1] * (1 - f) + g * f),
                                           int(panel[2] * (1 - f) + b_ * f), 255))
    draw_text(sheet, "64", 520, 20, (200, 200, 210, 255))
    draw_text(sheet, "32", 600, 20, (200, 200, 210, 255))
    out = os.path.join(art, "sentry_sheet.png")
    sheet.save(out)
    print("sheet  ", out)


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else os.path.join("TrekShuttle", "42")
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    build(root, os.path.join(here, "design", "art", "sentry"))
