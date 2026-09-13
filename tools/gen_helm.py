"""Generates the helm console: a texture and a one-tile world model.

The console stands in the bow of the cabin and is what the flight menu is
hung off. Like the shuttle it is a world model rather than a tile sprite, so
it needs no texture pack -- see gen_shuttle.py for why.

    python tools/gen_helm.py TrekShuttle/42
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pngwrite import Image, draw_text, draw_text_centered
from meshbuild import MeshBuilder

TEX_W = TEX_H = 128
UP_AXIS = "y"

HALF_BASE = 0.46
HALF_TOP  = 0.42
Y_BASE0, Y_BASE1 = 0.00, 0.34      # the pedestal
Y_DESK0, Y_DESK1 = 0.34, 0.78      # the slanted panel body
Y_HOOD0, Y_HOOD1 = 0.78, 1.06      # the screen hood

CASE      = (58, 62, 74, 255)
CASE_LITE = (92, 98, 114, 255)
CASE_DEEP = (30, 32, 40, 255)
BLACK     = (16, 17, 21, 255)
SCREEN    = (12, 26, 46, 255)
GRID      = (34, 74, 120, 255)

# The LCARS-ish palette: warm oranges and cool blues on black.
AMBER     = (238, 154, 62, 255)
SAND      = (222, 186, 122, 255)
LILAC     = (162, 146, 216, 255)
SKY       = (118, 176, 236, 255)
ROSE      = (204, 110, 118, 255)
BAR       = [AMBER, SAND, LILAC, SKY, ROSE]

REGIONS = {
    "panel": (0,  0,  64, 56),     # the sloped control surface, seen from above
    "screen": (68, 0, 128, 56),    # the upright display
    "case":  (0,  60, 64, 100),    # pedestal and sides
    "top":   (68, 60, 128, 100),
}


def lcars(img, x0, y0, x1, y1):
    """A block of rounded bars and readouts, the shape of a Starfleet panel."""
    img.rect(x0, y0, x1, y1, BLACK)
    w, h = x1 - x0, y1 - y0

    # the elbow: a thick coloured spine down the left with stubs off it
    img.rect(x0 + 2, y0 + 2, x0 + 9, y1 - 2, AMBER)
    for i in range(5):
        c = BAR[i % len(BAR)]
        yy = y0 + 3 + i * (h - 6) // 5
        img.rect(x0 + 10, yy, x0 + 10 + 6 + (i % 3) * 4, yy + (h - 6) // 5 - 2, c)

    # readout rows to the right of the spine
    for r in range((h - 8) // 6):
        yy = y0 + 4 + r * 6
        run = x0 + 30
        for i in range(4):
            c = BAR[(r + i) % len(BAR)]
            wd = 4 + ((r * 3 + i * 5) % 9)
            if run + wd > x1 - 3:
                break
            img.rect(run, yy, run + wd, yy + 4, c)
            run += wd + 2


def screen(img):
    x0, y0, x1, y1 = REGIONS["screen"]
    img.rect(x0, y0, x1, y1, BLACK)
    img.rect(x0 + 3, y0 + 3, x1 - 3, y1 - 3, SCREEN)
    # a wireframe horizon, the way every helm display in the show looked
    for i in range(y0 + 8, y1 - 5, 6):
        img.rect(x0 + 5, i, x1 - 5, i + 1, GRID)
    for i in range(x0 + 6, x1 - 5, 9):
        img.rect(i, y0 + 8, i + 1, y1 - 5, GRID)
    # a course plot
    img.rect(x0 + 12, y0 + 30, x0 + 20, y0 + 34, AMBER)
    img.rect(x0 + 30, y0 + 20, x0 + 36, y0 + 24, SKY)
    img.rect(x0 + 40, y0 + 12, x0 + 44, y0 + 16, ROSE)
    draw_text(img, "HELM", x0 + 5, y1 - 12, SAND, scale=1, spacing=1)


def build_atlas(path):
    img = Image(TEX_W, TEX_H, CASE_DEEP)
    lcars(img, *REGIONS["panel"])
    screen(img)

    x0, y0, x1, y1 = REGIONS["case"]
    img.rect(x0, y0, x1, y1, CASE)
    img.rect(x0, y0, x1, y0 + 2, CASE_LITE)
    img.rect(x0, y1 - 3, x1, y1, CASE_DEEP)
    for i in range(x0 + 6, x1 - 4, 12):        # louvres
        img.rect(i, y0 + 8, i + 5, y1 - 8, CASE_DEEP)

    x0, y0, x1, y1 = REGIONS["top"]
    img.rect(x0, y0, x1, y1, CASE)
    img.rect(x0 + 4, y0 + 4, x1 - 4, y1 - 4, CASE_LITE)
    img.save(path)


def build_mesh(path):
    m = MeshBuilder(TEX_W, TEX_H, up_axis=UP_AXIS)
    R = REGIONS
    P = m.place

    # pedestal
    m.box(HALF_BASE, Y_BASE0, Y_BASE1, (R["case"],) * 4,
          top_region=None, bottom_region=R["top"])
    # body, carrying the sloped panel on its top face
    m.box(HALF_TOP, Y_DESK0, Y_DESK1, (R["case"],) * 4, top_region=R["panel"])
    # the screen hood: a slab standing at the back, display facing south so it
    # looks out over whoever is standing at the console
    hb, hh = HALF_TOP * 0.92, 0.10
    m.quad(P(-hb, hh, Y_HOOD0), P(hb, hh, Y_HOOD0),
           P(hb, hh, Y_HOOD1), P(-hb, hh, Y_HOOD1), R["screen"], P(0, -1, 0))
    m.quad(P(hb, hh + 0.10, Y_HOOD0), P(-hb, hh + 0.10, Y_HOOD0),
           P(-hb, hh + 0.10, Y_HOOD1), P(hb, hh + 0.10, Y_HOOD1),
           R["case"], P(0, 1, 0))
    m.quad(P(-hb, hh, Y_HOOD1), P(hb, hh, Y_HOOD1),
           P(hb, hh + 0.10, Y_HOOD1), P(-hb, hh + 0.10, Y_HOOD1),
           R["top"], P(0, 0, 1))
    for sx in (-hb, hb):
        m.quad(P(sx, hh, Y_HOOD0), P(sx, hh + 0.10, Y_HOOD0),
               P(sx, hh + 0.10, Y_HOOD1), P(sx, hh, Y_HOOD1),
               R["case"], P(1 if sx > 0 else -1, 0, 0))

    return m.emit(path, "TREKHelm", "TREK_Helm.png")


if __name__ == "__main__":
    root = sys.argv[1]
    build_atlas(os.path.join(root, "media", "textures", "TREK_Helm.png"))
    nv, nf = build_mesh(os.path.join(root, "media", "models_X", "TREK_Helm.x"))
    print(f"helm console written: {nv} verts, {nf} tris")
