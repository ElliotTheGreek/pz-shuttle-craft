"""Generates the shuttlecraft texture atlas, mesh and inventory icon.

The shuttle is a world model, not a tile sprite -- the same choice the police
box made, and for the same reason: a tile would need a TileZed-packed texture
pack, while a model is a mesh plus a PNG and can be dropped on any square the
player can stand on.

Unlike the box it is *not* one tile.  The hull is authored 3 tiles wide and 5
long, which is the footprint TREK_Config asks the world for before it will
set the ship down.  Nothing in the engine enforces that -- a world model is
drawn from one square and overhangs the rest -- so the footprint check in Lua
and the numbers here have to be kept in step by hand.  They are both derived
from HULL_W / HULL_L below.

    python tools/gen_shuttle.py TrekShuttle/42
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pngwrite import Image, draw_text, draw_text_centered, text_width
from meshbuild import MeshBuilder
from import_gltf import import_glb

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
TYPE6_SOURCE = os.path.join(
    TOOLS_DIR, "assets", "type6_shuttle", "type6_shuttle.glb")

TEX_W = TEX_H = 256
UP_AXIS = "y"              # Project Zomboid world models are Y-up

# --- hull dimensions, in tiles -----------------------------------------
# Keep in step with C.Footprint in TREK_Config.lua.
HULL_W = 3.0               # port to starboard
HULL_L = 5.0               # bow to stern
HALF_W = HULL_W / 2 - 0.10
HALF_L = HULL_L / 2 - 0.15
NOSE_W = HALF_W * 0.52     # the bow is narrower than the beam

# Height matters more than it looks. Authored low and wide the hull read as a
# flat slab from the game's camera -- the police box is 2.1 tiles tall on a
# 0.9 tile base, and anything much squatter than about 1.5 disappears into
# the ground plane.
Y_SKID0, Y_SKID1 = 0.00, 0.16     # landing skids
Y_HULL0, Y_HULL1 = 0.16, 1.50     # main hull
Y_ROOF0, Y_ROOF1 = 1.50, 1.92     # dorsal spine
NAC_Y0,  NAC_Y1  = 0.30, 0.95     # nacelles, slung low and aft

REGISTRY = "1701/7"

# --- Starfleet hull palette --------------------------------------------
HULL      = (198, 200, 206, 255)
HULL_LITE = (226, 228, 233, 255)
HULL_DARK = (150, 153, 162, 255)
HULL_DEEP = (104, 107, 118, 255)
PANEL     = (172, 176, 186, 255)
TRIM      = (46, 74, 122, 255)      # Starfleet blue trim
TRIM_LITE = (86, 128, 190, 255)
GLASS     = (26, 40, 62, 255)
GLASS_LIT = (72, 118, 168, 255)
IMPULSE   = (232, 96, 44, 255)
IMPULSE_C = (255, 206, 150, 255)
WARP      = (86, 156, 226, 255)
WARP_CORE = (206, 232, 255, 255)
BLACK     = (22, 23, 27, 255)
DECAL     = (38, 40, 46, 255)

# Atlas regions (x0, y0, x1, y1).
#
# The two flanks get a region each rather than sharing one. A single region
# painted on both sides of a hull can be upright on both faces or at the same
# physical end on both, never both at once -- so the registry either came out
# backwards to starboard or ended up hidden behind a nacelle at the stern.
# Drawing the port face once and mirroring it into the starboard region costs
# a few kilobytes of atlas and settles it.
REGIONS = {
    "flank_p": (0,   0,   128, 88),
    "flank_s": (0,   92,  128, 180),
    "top":     (0,   184, 128, 252),
    "stern":   (132, 0,   212, 80),
    "bow":     (132, 84,  212, 154),
    "nacelle": (132, 158, 244, 196),
    "warp":    (216, 0,   248, 40),
    "roof":    (216, 44,  248, 84),
    "skid":    (216, 88,  248, 116),
    "under":   (216, 120, 248, 148),
}


def mirror_region(img, src, dst):
    """Copies one atlas region into another, flipped left to right."""
    sx0, sy0, sx1, sy1 = src
    dx0, dy0, dx1, dy1 = dst
    w, h = min(sx1 - sx0, dx1 - dx0), min(sy1 - sy0, dy1 - dy0)
    for y in range(h):
        for x in range(w):
            img.set(dx0 + (w - 1 - x), dy0 + y, img.get(sx0 + x, sy0 + y))


def _plate(img, x0, y0, x1, y1, base=PANEL):
    """A hull plate: lit top edge, shadowed bottom, seams all round."""
    img.rect(x0, y0, x1, y1, base)
    img.rect(x0, y0, x1, y0 + 1, HULL_LITE)
    img.rect(x0, y1 - 1, x1, y1, HULL_DEEP)
    img.frame(x0, y0, x1, y1, HULL_DARK, 1)


def _plating(img, region, rows=3, cols=6):
    """Fills a region with a grid of plates, so the hull is not flat grey."""
    x0, y0, x1, y1 = region
    img.rect(x0, y0, x1, y1, HULL)
    pw = (x1 - x0) / cols
    ph = (y1 - y0) / rows
    for r in range(rows):
        for c in range(cols):
            base = PANEL if (r + c) % 2 == 0 else HULL
            _plate(img, int(x0 + c * pw), int(y0 + r * ph),
                   int(x0 + (c + 1) * pw), int(y0 + (r + 1) * ph), base)


def flank(img):
    """The long side: cockpit glazing forward, registry amidships.

    Everything legible is kept in the forward two-thirds. The nacelles hang
    over the aft-lower flank, and the first pass put the registry straight
    behind one of them where nothing could ever see it.
    """
    R = REGIONS["flank_p"]
    x0, y0, x1, y1 = R
    w, h = x1 - x0, y1 - y0
    _plating(img, R, rows=4, cols=8)

    # The blue trim stripe that runs the length of the hull.
    img.rect(x0, y0 + int(h * 0.34), x1, y0 + int(h * 0.43), TRIM)
    img.rect(x0, y0 + int(h * 0.34), x1, y0 + int(h * 0.37), TRIM_LITE)

    # Cockpit glazing, forward (the bow is at u=0, the left of this face).
    gy0, gy1 = y0 + 8, y0 + 28
    img.rect(x0 + 5, gy0, x0 + 56, gy1, BLACK)
    for i in range(3):
        px = x0 + 8 + i * 16
        img.rect(px, gy0 + 2, px + 13, gy1 - 2, GLASS)
        img.rect(px, gy0 + 2, px + 13, gy0 + 6, GLASS_LIT)

    # Two square viewports amidships, still clear of the nacelle.
    for i in range(2):
        px = x0 + 66 + i * 22
        img.rect(px, y0 + 10, px + 15, y0 + 26, BLACK)
        img.rect(px + 2, y0 + 12, px + 13, y0 + 24, GLASS)

    # Registry, painted on the plating below the stripe and forward of the
    # nacelle, which covers this face from about u=0.45 aft. Drawn large
    # enough to survive the face being nearly five tiles long: at scale 1 the
    # glyphs come out well under a fifth of a tile and read as noise.
    draw_text(img, "NCC", x0 + 6, y0 + int(h * 0.48), HULL_DEEP, scale=1, spacing=1)
    draw_text(img, REGISTRY, x0 + 6, y0 + int(h * 0.60), DECAL, scale=2, spacing=1)
    # A Starfleet pennant block forward of the lettering.
    img.rect(x0 + 6, y0 + int(h * 0.88), x0 + 40, y0 + int(h * 0.95), TRIM)


def stern(img):
    """The hatch face, with the impulse vents either side of it."""
    R = REGIONS["stern"]
    x0, y0, x1, y1 = R
    w = x1 - x0
    _plating(img, R, rows=4, cols=4)
    img.rect(x0, y0 + 28, x1, y0 + 38, TRIM)

    # the ramp, centred
    rx0, rx1 = x0 + int(w * 0.24), x1 - int(w * 0.24)
    img.rect(rx0, y0 + 40, rx1, y1 - 4, HULL_DARK)
    img.frame(rx0, y0 + 40, rx1, y1 - 4, HULL_DEEP, 2)
    img.rect(rx0 + 6, y0 + 46, rx1 - 6, y0 + 60, GLASS)
    for i in range(4):                       # ramp treads
        img.rect(rx0 + 4, y0 + 66 + i * 5, rx1 - 4, y0 + 68 + i * 5, HULL_DEEP)

    # impulse vents, one each side of the ramp
    for side in (0, 1):
        vx0 = x0 + 4 if side == 0 else rx1 + 4
        vx1 = rx0 - 4 if side == 0 else x1 - 4
        img.rect(vx0, y0 + 44, vx1, y0 + 64, BLACK)
        img.rect(vx0 + 2, y0 + 46, vx1 - 2, y0 + 62, IMPULSE)
        img.rect(vx0 + 4, y0 + 50, vx1 - 4, y0 + 58, IMPULSE_C)


def bow(img):
    """The nose: one wide forward window under a brow of plating."""
    R = REGIONS["bow"]
    x0, y0, x1, y1 = R
    _plating(img, R, rows=3, cols=3)
    img.rect(x0, y0 + 26, x1, y0 + 33, TRIM)
    img.rect(x0 + 5, y0 + 10, x1 - 5, y0 + 24, BLACK)
    img.rect(x0 + 7, y0 + 12, x1 - 7, y0 + 22, GLASS)
    img.rect(x0 + 7, y0 + 12, x1 - 7, y0 + 15, GLASS_LIT)
    # a pair of forward floods
    for px in (x0 + 12, x1 - 20):
        img.rect(px, y1 - 18, px + 8, y1 - 12, IMPULSE_C)


def simple(img, region, base, stripe=None, rows=2, cols=4):
    _plating(img, region, rows=rows, cols=cols)
    x0, y0, x1, y1 = region
    if base is not HULL:
        img.rect(x0, y0, x1, y1, base)
        img.frame(x0, y0, x1, y1, HULL_DEEP, 1)
    if stripe:
        img.rect(x0, y0 + (y1 - y0) // 2 - 3, x1, y0 + (y1 - y0) // 2 + 3, stripe)


def nacelle(img):
    """The flank pods: dark housing with a lit warp grille along the top."""
    R = REGIONS["nacelle"]
    x0, y0, x1, y1 = R
    img.rect(x0, y0, x1, y1, HULL_DARK)
    img.rect(x0, y0, x1, y0 + 3, HULL_LITE)
    img.rect(x0, y1 - 4, x1, y1, HULL_DEEP)
    # grille
    gy0, gy1 = y0 + 12, y0 + 26
    img.rect(x0 + 6, gy0, x1 - 6, gy1, BLACK)
    img.rect(x0 + 8, gy0 + 2, x1 - 8, gy1 - 2, WARP)
    for i in range(x0 + 10, x1 - 10, 7):
        img.rect(i, gy0 + 4, i + 3, gy1 - 4, WARP_CORE)
    img.rect(x0, y1 - 14, x1, y1 - 10, TRIM)


def warp_end(img):
    R = REGIONS["warp"]
    x0, y0, x1, y1 = R
    img.rect(x0, y0, x1, y1, BLACK)
    img.rect(x0 + 4, y0 + 4, x1 - 4, y1 - 4, WARP)
    img.rect(x0 + 10, y0 + 10, x1 - 10, y1 - 10, WARP_CORE)


def build_atlas(path):
    img = Image(TEX_W, TEX_H, HULL_DEEP)
    flank(img)
    mirror_region(img, REGIONS["flank_p"], REGIONS["flank_s"])
    stern(img)
    bow(img)
    simple(img, REGIONS["top"], HULL, rows=3, cols=3)
    simple(img, REGIONS["roof"], HULL_DARK, stripe=TRIM)
    nacelle(img)
    warp_end(img)
    simple(img, REGIONS["skid"], HULL_DEEP, rows=1, cols=2)
    simple(img, REGIONS["under"], HULL_DEEP, rows=1, cols=1)
    img.save(path)
    return img


def build_mesh(path):
    """The hull as a tapered body, a dorsal spine, two nacelles and skids.

    Project Zomboid world models are Y-up and 1 unit is one tile, so the
    numbers here are the shuttle's real footprint. `place(east, north, up)`
    does the axis swap.
    """
    m = MeshBuilder(TEX_W, TEX_H, up_axis=UP_AXIS)
    R = REGIONS
    P = m.place

    # --- main hull: a box whose bow end is pinched in ---------------------
    # north (+north) is the bow, so the +Y end of the body is narrow.
    # MeshBuilder.quad maps its four points to texture corners in the fixed
    # order (0,1) (1,1) (1,0) (0,0), so v=1 is the *bottom* of the region.
    # Every wall face therefore has to be given bottom-left, bottom-right,
    # top-right, top-left in that order. Reversing the winding to turn a
    # normal around also turns the artwork upside down, which is exactly what
    # it did to the registry on the starboard flank; the normal is passed
    # explicitly instead.
    a_s, a_n = HALF_L, -HALF_L        # stern is +north here, bow is -north
    # port flank -- bow at u=0
    m.quad(P(-NOSE_W, a_n, Y_HULL0), P(-HALF_W, a_s, Y_HULL0),
           P(-HALF_W, a_s, Y_HULL1), P(-NOSE_W, a_n, Y_HULL1),
           R["flank_p"], P(-1, 0, 0))
    # starboard flank, which reads from its own pre-mirrored region so the
    # registry sits forward and upright on this side as well
    m.quad(P(NOSE_W, a_n, Y_HULL0), P(HALF_W, a_s, Y_HULL0),
           P(HALF_W, a_s, Y_HULL1), P(NOSE_W, a_n, Y_HULL1),
           R["flank_s"], P(1, 0, 0))
    # stern, carrying the ramp
    m.quad(P(-HALF_W, a_s, Y_HULL0), P(HALF_W, a_s, Y_HULL0),
           P(HALF_W, a_s, Y_HULL1), P(-HALF_W, a_s, Y_HULL1),
           R["stern"], P(0, 1, 0))
    # bow
    m.quad(P(-NOSE_W, a_n, Y_HULL0), P(NOSE_W, a_n, Y_HULL0),
           P(NOSE_W, a_n, Y_HULL1), P(-NOSE_W, a_n, Y_HULL1),
           R["bow"], P(0, -1, 0))
    # deck head
    m.quad(P(-HALF_W, a_s, Y_HULL1), P(HALF_W, a_s, Y_HULL1),
           P(NOSE_W, a_n, Y_HULL1), P(-NOSE_W, a_n, Y_HULL1),
           R["top"], P(0, 0, 1))
    # belly
    m.quad(P(-NOSE_W, a_n, Y_HULL0), P(NOSE_W, a_n, Y_HULL0),
           P(HALF_W, a_s, Y_HULL0), P(-HALF_W, a_s, Y_HULL0),
           R["under"], P(0, 0, -1))

    # --- dorsal spine, set in from the hull edge --------------------------
    sw, sl = HALF_W * 0.62, HALF_L * 0.66
    m.quad(P(-sw, sl, Y_ROOF0), P(-sw * 0.7, -sl, Y_ROOF0),
           P(-sw * 0.7, -sl, Y_ROOF1), P(-sw, sl, Y_ROOF1), R["roof"], P(-1, 0, 0))
    m.quad(P(sw, sl, Y_ROOF1), P(sw * 0.7, -sl, Y_ROOF1),
           P(sw * 0.7, -sl, Y_ROOF0), P(sw, sl, Y_ROOF0), R["roof"], P(1, 0, 0))
    m.quad(P(-sw, sl, Y_ROOF0), P(sw, sl, Y_ROOF0),
           P(sw, sl, Y_ROOF1), P(-sw, sl, Y_ROOF1), R["roof"], P(0, -1, 0))
    m.quad(P(sw * 0.7, -sl, Y_ROOF0), P(-sw * 0.7, -sl, Y_ROOF0),
           P(-sw * 0.7, -sl, Y_ROOF1), P(sw * 0.7, -sl, Y_ROOF1),
           R["roof"], P(0, 1, 0))
    m.quad(P(-sw, sl, Y_ROOF1), P(sw, sl, Y_ROOF1),
           P(sw * 0.7, -sl, Y_ROOF1), P(-sw * 0.7, -sl, Y_ROOF1),
           R["top"], P(0, 0, 1))

    # --- nacelles, one on each flank -------------------------------------
    # Aft-biased on purpose: run forward as well and they sit straight over
    # the registry and the cockpit glazing, which is where the first pass put
    # them and why neither could be seen.
    n_fwd, n_aft = -HALF_L * 0.10, HALF_L * 0.94
    for side in (-1, 1):
        x_in = side * (HALF_W - 0.02)
        x_out = side * (HALF_W + 0.28)
        lo, hi = min(x_in, x_out), max(x_in, x_out)
        # outboard face
        m.quad(P(x_out, n_fwd, NAC_Y0), P(x_out, n_aft, NAC_Y0),
               P(x_out, n_aft, NAC_Y1), P(x_out, n_fwd, NAC_Y1),
               R["nacelle"], P(side, 0, 0), flip_u=(side > 0))
        # top and bottom
        m.quad(P(lo, n_aft, NAC_Y1), P(hi, n_aft, NAC_Y1),
               P(hi, n_fwd, NAC_Y1), P(lo, n_fwd, NAC_Y1),
               R["nacelle"], P(0, 0, 1))
        m.quad(P(lo, n_fwd, NAC_Y0), P(hi, n_fwd, NAC_Y0),
               P(hi, n_aft, NAC_Y0), P(lo, n_aft, NAC_Y0),
               R["nacelle"], P(0, 0, -1))
        # the lit grille ends, fore and aft
        m.quad(P(lo, n_fwd, NAC_Y0), P(hi, n_fwd, NAC_Y0),
               P(hi, n_fwd, NAC_Y1), P(lo, n_fwd, NAC_Y1),
               R["warp"], P(0, -1, 0))
        m.quad(P(hi, n_aft, NAC_Y0), P(lo, n_aft, NAC_Y0),
               P(lo, n_aft, NAC_Y1), P(hi, n_aft, NAC_Y1),
               R["warp"], P(0, 1, 0))

    # --- landing skids ----------------------------------------------------
    for side in (-1, 1):
        for fore in (-1, 1):
            cx = side * HALF_W * 0.66
            cy = fore * HALF_L * 0.58
            m.box(0.14, Y_SKID0, Y_SKID1, (R["skid"],) * 4,
                  top_region=R["skid"], bottom_region=R["under"])
            # box() is centred on the origin, so shift the four verts it just
            # made into place rather than re-deriving the geometry.
            for i in range(len(m.verts) - 24, len(m.verts)):
                x, y, z = m.verts[i]
                m.verts[i] = (x + cx, y, z + cy)

    nv, nf = m.emit(path, "TREKShuttle", "TREK_Shuttle.png")
    return nv, nf


def build_icon(path):
    """64x64 inventory icon: the shuttle seen three-quarters from above."""
    img = Image(64, 64, (0, 0, 0, 0))
    # hull, drawn as a tapering stack of rows so the bow narrows
    for i, y in enumerate(range(12, 54)):
        t = i / 41.0
        half = int(6 + 12 * t)                # narrow at the top (bow)
        img.rect(32 - half, y, 32 + half, y + 1, HULL if i % 6 else PANEL)
    # trim stripe
    img.rect(10, 34, 54, 38, TRIM)
    # cockpit glass at the bow
    img.rect(25, 15, 39, 23, BLACK)
    img.rect(26, 16, 38, 22, GLASS)
    img.rect(26, 16, 38, 18, GLASS_LIT)
    # nacelles
    for x0 in (5, 51):
        img.rect(x0, 26, x0 + 8, 50, HULL_DARK)
        img.rect(x0 + 1, 30, x0 + 7, 44, BLACK)
        img.rect(x0 + 2, 31, x0 + 6, 43, WARP)
        img.rect(x0 + 3, 33, x0 + 5, 41, WARP_CORE)
    # stern ramp and impulse vents
    img.rect(24, 48, 40, 58, HULL_DARK)
    img.frame(24, 48, 40, 58, HULL_DEEP, 1)
    for x0 in (14, 42):
        img.rect(x0, 50, x0 + 8, 56, IMPULSE)
        img.rect(x0 + 2, 51, x0 + 6, 55, IMPULSE_C)
    # registry, tiny
    draw_text_centered(img, "1701", 32, 40, DECAL, scale=1, spacing=0)
    img.save(path)


if __name__ == "__main__":
    root = sys.argv[1]
    texture_path = os.path.join(root, "media", "textures", "TREK_Shuttle.png")
    mesh_path = os.path.join(root, "media", "models_X", "TREK_Shuttle.x")
    nv, nf, width, length, height = import_glb(
        TYPE6_SOURCE, mesh_path, texture_path, "TREK_Shuttle.png",
        target_length=HULL_L, target_width=HULL_W)

    build_icon(os.path.join(root, "media", "ui", "TREK_Shuttle.png"))
    build_icon(os.path.join(root, "media", "textures", "Item_TREK_Shuttle.png"))
    print(f"shuttle: texture, icon and mesh written "
          f"({nv} verts, {nf} tris, {width:.2f}x{length:.2f}x{height:.2f} tiles, "
          f"reserved footprint={HULL_W:.0f}x{HULL_L:.0f}, up-axis={UP_AXIS})")
