"""The shuttle's hull: one mesh built here, in eighteen skins, and what a vehicle needs beside them.

    python tools/gen_shuttle.py
        TrekShuttle/42/media/models_X/TREK_Shuttle.x          the hull, as the vehicle draws it
        TrekShuttle/42/media/models_X/TREK_ShuttleHull.x      the same hull, as a world model draws it
        TrekShuttle/42/media/textures/TREK_Shuttle*.png       a sheet for each skin, 512 square
        TrekShuttle/42/media/scripts/vehicles/trekshuttle_vehicle.txt   its skin blocks, rewritten
        TrekShuttle/42/media/ui/TREK_Shuttle.png, textures/Item_TREK_Shuttle.png   the icon
        (and, through tools/gen_vehicle_assets.py: the mask, the seat chart, the empty wheel)
        design/art/shuttle/                                   LOOK AT THESE: shuttle_skins.png,
                                                              shuttle_a.png, shuttle_b.png, shuttle_sheet.png

**She is built here, from scratch, the Mechs mod's way** (pz-mechs ART.md 6.5 and 6.11,
tools/hullkit.py): flat faces and hard corners, one mesh, and a sheet for each *livery* and each
*state* of wear. Until 1.22 she was a mesh an image-to-3D model made (tools/assets/type6_shuttle,
still kept), in one skin that could not be changed. A skin's index is what the vehicle script
lists and what the engine keeps; which one a ship wears is V.skinFor in TREK_Vehicle.lua.

  * **Y is up, the nose is +Z** (a vehicle's forward) and **1 unit is 1 square**.
  * She stands on y = 0 and is centred fore and aft and side to side: the vehicle rides half a
    square up on wheels nobody sees, so her nacelles hang clear of the road.
  * **3 wide by 5 long**: HULL_W and HULL_L are C.Footprint in TREK_Config.lua, the room the
    world is asked for before she is set down, and tests/test_layout.py holds the two together.
    The vehicle script's extents length is the mesh's (tests/test_assets.py).
  * **+e is her starboard side.** (east, north, up) is how she is written here, and from the
    east looking west north is on the right: so a face's corners are given as somebody outside
    sees them, and what is lettered on her reads the right way round. Each flank has its own
    picture, because one picture cannot be right on two opposite faces.
  * **The order of SKINS is the skin index, which the engine saves: append, never reorder.**
    C.HullLiveries and C.HullStates in TREK_Config.lua are held to it here.

Her body is a loft: five stations from stern to nose, each a half outline of four corners (her
belly's edge, her waist, her shoulder, her roof's edge), joined by flat faces. Her nacelles are
boxes slung under her waist on a pylon each. The pictures cull faces as the engine does, so one
wound the wrong way is a hole in the picture.
"""
import os
import re
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from meshbuild import MeshBuilder                                   # noqa: E402
import hullkit as kit                                               # noqa: E402
from hullkit import BLACK, DARK, STEEL, STATES, tone, seams         # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEDIA = os.path.join(ROOT, "TrekShuttle", "42", "media")
ART = os.path.join(ROOT, "design", "art", "shuttle")
VEHICLE = os.path.join(MEDIA, "scripts", "vehicles", "trekshuttle_vehicle.txt")
CONFIG = os.path.join(MEDIA, "lua", "shared", "TREK", "TREK_Config.lua")

TEX = 512                  # the vehicle shader's cap, at the game's default setting

# --- the room she takes, in squares --------------------------------------
# Keep in step with C.Footprint in TREK_Config.lua.
HULL_W = 3.0               # port to starboard, over her nacelles
HULL_L = 5.0               # stern to nose

NUMBER = "07"

# A livery: her paint, her trim, and how the trim is laid ("pin": two thin lines; "band": one
# broad one). The first is the fleet's own, and the one every ship wore before there were skins.
HOUSING = (112, 116, 124)
LIVERIES = {
    "fleet":    dict(base=(206, 208, 204), trim=(158, 46, 40), lay="pin"),
    "sciences": dict(base=(206, 208, 204), trim=(44, 104, 150), lay="band"),
    "ops":      dict(base=(206, 208, 204), trim=(198, 152, 48), lay="band"),
    "medical":  dict(base=(214, 216, 212), trim=(38, 132, 120), lay="band"),
    "tactical": dict(base=(96, 102, 112), trim=(168, 58, 46), lay="pin"),
    "survey":   dict(base=(178, 156, 114), trim=(70, 60, 50), lay="band"),
}
SKINS = [(livery, state) for livery in LIVERIES for state in STATES]
SCORCH = 0.8               # how far her corrosion is burnt black and not rust: she was never iron


def skin_name(i):
    """The texture of skin `i`. The first keeps the name the vehicle script has always had."""
    livery, state = SKINS[i]
    return "TREK_Shuttle" if i == 0 else "TREK_Shuttle_%s_%s" % (livery, state)


# --- the hull, in squares: e across (+ is starboard), n along (+ is forward), h up ---
N0, N1 = -HULL_L / 2, HULL_L / 2
HB, HT = 0.45, 2.05                         # her belly and her roof
EW = 1.10                                   # half her beam at the waist
# Stations: where along her, then her belly's edge, her waist, her shoulder and her roof's edge,
# each (how far out, how far up).
STATIONS = [
    (N0,    (0.80, 0.62), (1.00, 0.85), (1.00, 1.30), (0.66, 1.52)),    # her stern's face
    (-1.95, (0.90, HB),   (EW, 0.75),   (EW, 1.45),   (0.80, HT)),
    (0.75,  (0.90, HB),   (EW, 0.75),   (EW, 1.45),   (0.80, HT)),      # the head of her windscreen
    (1.85,  (0.80, 0.50), (0.98, 0.78), (0.98, 1.22), (0.66, 1.42)),    # its foot
    (N1,    (0.52, 0.66), (0.66, 0.82), (0.66, 1.00), (0.46, 1.08)),    # the tip of her nose
]
NACELLE = (1.02, HULL_W / 2, -2.40, 1.05, 0.0, 0.50)     # e inner, e outer, n0, n1, h0, h1
PYLON = (1.02, 1.30, -1.70, 0.30, 0.50, 0.84)
POD = (-0.36, -1.55, 0.36, -0.55, HT, HT + 0.16)         # e0, n0, e1, n1, h0, h1: a sensor housing

# Regions of the sheet (x0, y0, x1, y1): 72 pixels to a square along her flank.
R = {
    "flank_s": (0, 0, 360, 116),        # her starboard side, stern at the left
    "flank_p": (0, 120, 360, 236),      # her port side, nose at the left
    "top":     (0, 240, 360, 398),      # from above, stern at the left, port at the top
    "stern":   (364, 0, 512, 80),       # from behind
    "nose":    (364, 84, 460, 120),     # from ahead
    "plain":   (364, 124, 512, 180),
    "dark":    (364, 184, 440, 236),
    "nacelle": (0, 402, 250, 438),      # a nacelle's outer side, stern at the left
    "nactop":  (0, 442, 250, 470),
    "bussard": (254, 402, 290, 438),    # a nacelle's front
    "exhaust": (294, 402, 330, 438),    # and its end
    "pod":     (334, 402, 406, 418),
    "podtop":  (334, 422, 406, 470),
}
# What weathers as paint does, and whether dirt climbs it from the bottom (a roof has no bottom).
PAINTED = {"flank_s": True, "flank_p": True, "stern": True, "plain": True, "nacelle": True,
           "top": False, "nose": False, "nactop": False, "pod": False, "podtop": False}
IN_HOUSING = ("nacelle", "nactop", "pod", "podtop")


# Where a place on her is in each picture, in pixels of the sheet.
def uv_flank(side):
    x0, y0, x1, y1 = R["flank_s" if side > 0 else "flank_p"]

    def at(e, n, h):
        along = (n - N0) / HULL_L if side > 0 else (N1 - n) / HULL_L
        return (x0 + along * (x1 - x0), y0 + (HT - h) / (HT - HB) * (y1 - y0))
    return at


def uv_top(e, n, h):
    x0, y0, x1, y1 = R["top"]
    return (x0 + (n - N0) / HULL_L * (x1 - x0), y0 + (e + EW) / (2 * EW) * (y1 - y0))


STERN_H = (0.50, 1.60)
NOSE_H = (0.60, 1.10)
NOSE_E = 0.70


def uv_stern(e, n, h):
    x0, y0, x1, y1 = R["stern"]
    return (x0 + (e + EW) / (2 * EW) * (x1 - x0), y0 + (STERN_H[1] - h) / (STERN_H[1] - STERN_H[0]) * (y1 - y0))


def uv_nose(e, n, h):
    x0, y0, x1, y1 = R["nose"]
    return (x0 + (NOSE_E - e) / (2 * NOSE_E) * (x1 - x0), y0 + (NOSE_H[1] - h) / (NOSE_H[1] - NOSE_H[0]) * (y1 - y0))


def fx(n):
    """Where a place along her is across her starboard flank's picture, and across her top's."""
    return int(round((n - N0) / HULL_L * 360))


def fy(h):
    return int(round((HT - h) / (HT - HB) * 116))


def ty(e):
    return int(round((e + EW) / (2 * EW) * 158))


# The glass, which is black: on a flank (in the starboard picture's own pixels; the port one is
# its mirror), and from above, the three panes of her windscreen.
FLANK_GLASS = [(fx(-1.25), 9, fx(-0.70), 35), (fx(-0.45), 9, fx(0.10), 35), (fx(0.80), 6, fx(1.80), 56)]
TOP_GLASS = [(fx(0.80), ty(-0.74) + 34 * i, fx(1.80), ty(-0.74) + 34 * i + 30) for i in range(3)]


# ------------------------------------------------------------------------------ the sheets
def build_sheet(livery, state):
    """One skin: the paint, what is drawn on it, the weather, then the glass and what glows."""
    L = LIVERIES[livery]
    base, trim = L["base"], L["trim"]
    line, lite = tone(base, 0.70), tone(base, 1.08)
    img = Image.new("RGB", (TEX, TEX), DARK)

    def region(name, painter, seed):
        x0, y0, x1, y1 = R[name]
        w, h = x1 - x0, y1 - y0
        if name == "dark":
            tile = Image.new("RGB", (w, h), DARK)
        else:
            colour = HOUSING if name in IN_HOUSING else tone(base, 0.90 if name == "top" else 1.0)
            tile = Image.fromarray(kit.paint(w, h, colour, seed).astype(np.uint8))
        painter(ImageDraw.Draw(tile), w, h)
        img.paste(tile, (x0, y0))

    def stripe(d, x0, x1, y):
        """Her trim along a face, its middle at row `y`."""
        if L["lay"] == "pin":
            d.rectangle([x0, y - 5, x1, y - 4], fill=trim)
            d.rectangle([x0, y + 3, x1, y + 4], fill=trim)
        else:
            d.rectangle([x0, y - 5, x1, y + 4], fill=trim)

    def flank(mirror):
        def painter(d, w, h):
            def X(a, b):
                return (w - 1 - b, w - 1 - a) if mirror else (a, b)

            def box(a, y0, b, y1, **kw):
                xa, xb = X(a, b)
                d.rectangle([xa, y0, xb, y1], **kw)

            for n in (-1.95, -0.95, 0.75, 1.85):                               # her frames
                box(fx(n), 0, fx(n), h - 1, fill=line)
            for y in (fy(1.45), fy(0.75)):                                     # her shoulder and her waist
                d.line([(0, y), (w - 1, y)], fill=line)
                d.line([(0, y + 1), (w - 1, y + 1)], fill=lite)
            d.rectangle([0, fy(0.75) + 2, w - 1, h - 1], fill=tone(base, 0.74))  # her keel, darker
            d.rectangle([0, 0, w - 1, h - 1], outline=line)
            stripe(d, 0, w - 1, fy(1.22))
            box(fx(-0.60), fy(1.43), fx(0.20), fy(0.78), fill=None, outline=BLACK)   # her side door
            box(fx(-0.60) + 4, fy(1.0), fx(-0.60) + 9, fy(0.92), fill=STEEL)          # and its handle
            for y in range(fy(1.38), fy(0.84), 6):                             # a grille, aft, as paint
                box(fx(-2.30), y, fx(-2.05), y, fill=tone(base, 0.45))
            xa, _ = X(fx(1.02), fx(1.02) + kit.text_width(NUMBER, 3))
            kit.text(d, NUMBER, xa, fy(1.05), BLACK, 3)                        # her number, under her pilot's window
        return painter

    def top(d, w, h):
        seams(d, w, h, 5, 2, line, lite)
        d.line([(fx(0.75), 0), (fx(0.75), h - 1)], fill=BLACK)                 # where her windscreen begins
        d.line([(fx(1.85), 0), (fx(1.85), h - 1)], fill=BLACK)                 # and her nose
        d.rectangle([fx(1.85) + 2, ty(0) - 5, w - 1, ty(0) + 4], fill=trim)    # her trim, down her nose
        for x in range(fx(-2.45), fx(-2.0), 5):                                # her after slope breathes
            d.line([(x, ty(-0.5)), (x, ty(0.5))], fill=tone(base, 0.45))
        d.rectangle([fx(-0.35), ty(-0.42), fx(0.45), ty(0.42)], outline=BLACK)   # a roof hatch
        kit.text(d, NUMBER, fx(-0.28), ty(0) - 10, BLACK, 3)

    def stern(d, w, h):
        seams(d, w, h, 1, 1, line, lite)
        stripe(d, 0, w - 1, 20)
        d.rectangle([44, 27, 103, 72], fill=tone(base, 0.86), outline=BLACK)   # her hatch
        for y in range(52, 70, 5):                                             # its treads
            d.line([(50, y), (97, y)], fill=line)
        kit.text(d, NUMBER, 74 - kit.text_width(NUMBER, 2) // 2, 32, BLACK, 2)

    def nose(d, w, h):
        seams(d, w, h, 1, 1, line, lite)
        d.rectangle([0, 0, w - 1, 5], fill=trim)

    def nacelle(d, w, h):
        d.rectangle([0, 0, w - 1, h - 1], outline=BLACK)
        d.rectangle([0, h - 8, w - 1, h - 6], fill=trim)
        d.line([(fx(-1.0) - 7, 0), (fx(-1.0) - 7, h - 1)], fill=BLACK)

    def nactop(d, w, h):
        d.rectangle([0, 0, w - 1, h - 1], outline=BLACK)
        for x in range(30, w - 20, 44):
            d.line([(x, 0), (x, h - 1)], fill=tone(HOUSING, 0.7))

    def pod(d, w, h):
        d.rectangle([0, 0, w - 1, h - 1], outline=BLACK)

    def podtop(d, w, h):
        d.rectangle([0, 0, w - 1, h - 1], outline=BLACK)
        d.rectangle([10, 10, w - 11, h - 11], fill=DARK, outline=BLACK)
        for x in range(14, w - 14, 6):
            d.line([(x, 12), (x, h - 13)], fill=STEEL)

    def plain(d, w, h):
        d.rectangle([0, 0, w - 1, h - 1], outline=line)

    def dark(d, w, h):
        pass

    for seed, (name, painter) in enumerate([
            ("flank_s", flank(False)), ("flank_p", flank(True)), ("top", top), ("stern", stern), ("nose", nose),
            ("plain", plain), ("dark", dark), ("nacelle", nacelle), ("nactop", nactop),
            ("bussard", dark), ("exhaust", dark), ("pod", pod), ("podtop", podtop)]):
        region(name, painter, 2100 + seed)

    img = kit.weather(img, R, PAINTED, state, 8100, scorch=SCORCH)

    def put(name, box):
        x0, y0 = R[name][0], R[name][1]
        return (x0 + box[0], y0 + box[1], x0 + box[2], y0 + box[3])

    w = R["flank_s"][2] - R["flank_s"][0]
    for i, (a, y0, b, y1) in enumerate(FLANK_GLASS):
        kit.pane(img, put("flank_s", (a, y0, b, y1)), state, 8900 + i, cracked=(state == "derelict" and i == 0))
        kit.pane(img, put("flank_p", (w - b, y0, w - a, y1)), state, 8910 + i, cracked=(state == "derelict" and i == 2))
    for i, box in enumerate(TOP_GLASS):
        kit.pane(img, put("top", box), state, 8920 + i, cracked=(state == "derelict" and i == 1))
    # What glows: her impulse vents either side of her hatch and her tail lamps, her floods, the
    # grille down each nacelle, its collector and its end. On a derelict all of it is out.
    for box in ((10, 34, 36, 58), (112, 34, 138, 58)):
        kit.lamp(img, put("stern", box), (232, 104, 48), state)
    for box in ((12, 64, 28, 72), (120, 64, 136, 72)):
        kit.lamp(img, put("stern", box), (170, 44, 38), state)
    for box in ((10, 16, 30, 28), (66, 16, 86, 28)):
        kit.lamp(img, put("nose", box), (236, 222, 170), state)
    kit.lamp(img, put("nacelle", (22, 8, 150, 20)), (88, 158, 228), state)
    kit.lamp(img, put("bussard", (0, 0, 36, 36)), DARK, state)
    kit.lamp(img, put("bussard", (5, 5, 31, 31)), (214, 70, 40), state)
    kit.lamp(img, put("bussard", (12, 12, 24, 24)), (250, 170, 110), state)
    kit.lamp(img, put("exhaust", (0, 0, 36, 36)), DARK, state)
    kit.lamp(img, put("exhaust", (6, 6, 30, 30)), (88, 158, 228), state)
    return img.convert("RGBA")


# ------------------------------------------------------------------------------ the mesh
def hull_mesh():
    """Her hull, wound as meshbuild leaves a mesh (which is how a world model is drawn the right
    way out). A vehicle's is this turned whole (kit.for_vehicle)."""
    m = MeshBuilder(TEX, TEX, up_axis="y")
    P = m.place
    middle = np.array((0.0, 0.0, 1.2))

    def face(points, at, outward=None):
        """A flat face from its corners, in (e, n, h), and where each is in the sheet. The corners
        are put the way round somebody outside sees them, whichever way they were given."""
        pts = [np.array(p, np.float64) for p in points]
        px = [at(*p) for p in points]
        normal = np.cross(pts[1] - pts[0], pts[2] - pts[0])
        normal /= np.linalg.norm(normal)
        out = np.array(outward, np.float64) if outward is not None else (sum(pts) / len(pts) - middle) * (1, 0, 1)
        if np.dot(normal, out) < 0:
            pts, px, normal = pts[::-1], px[::-1], -normal
        first = len(m.verts)
        for p, (u, v) in zip(pts, px):
            m.verts.append(P(*p))
            m.norms.append(P(*normal))
            m.uvs.append((u / TEX, v / TEX))
        for i in range(1, len(pts) - 1):
            m.faces.append((first, first + i, first + i + 1))

    def rect(name, flip=False):
        """Corners given bottom left, bottom right, top right, top left wear the whole of a region."""
        x0, y0, x1, y1 = R[name]
        if flip:
            x0, x1 = x1, x0
        corners = [(x0, y1), (x1, y1), (x1, y0), (x0, y0)]
        it = iter(corners)
        return lambda e, n, h: next(it)

    def box(e0, n0, e1, n1, h0, h1, sides, top, front, back, under="dark", flip=False):
        """`sides` has its stern at the left on the +e side."""
        face([(e1, n0, h0), (e1, n1, h0), (e1, n1, h1), (e1, n0, h1)], rect(sides, flip), (1, 0, 0))
        face([(e0, n1, h0), (e0, n0, h0), (e0, n0, h1), (e0, n1, h1)], rect(sides, not flip), (-1, 0, 0))
        face([(e0, n0, h0), (e1, n0, h0), (e1, n0, h1), (e0, n0, h1)], rect(back), (0, -1, 0))
        face([(e1, n1, h0), (e0, n1, h0), (e0, n1, h1), (e1, n1, h1)], rect(front), (0, 1, 0))
        face([(e1, n0, h1), (e1, n1, h1), (e0, n1, h1), (e0, n0, h1)], rect(top), (0, 0, 1))
        face([(e0, n1, h0), (e1, n1, h0), (e1, n0, h0), (e0, n0, h0)], rect(under), (0, 0, -1))

    def dark_at(e, n, h):
        x0, y0, x1, y1 = R["dark"]
        return ((x0 + x1) / 2 + e * 8, (y0 + y1) / 2 + n * 4)

    # The body: between each pair of stations, three bands down each side, her roof and her belly.
    for (na, *a), (nb, *b) in zip(STATIONS, STATIONS[1:]):
        for s in (1, -1):
            at = uv_flank(s)
            for k in range(3):
                face([(s * a[k][0], na, a[k][1]), (s * b[k][0], nb, b[k][1]),
                      (s * b[k + 1][0], nb, b[k + 1][1]), (s * a[k + 1][0], na, a[k + 1][1])], at)
        face([(a[3][0], na, a[3][1]), (b[3][0], nb, b[3][1]), (-b[3][0], nb, b[3][1]), (-a[3][0], na, a[3][1])], uv_top, (0, 0, 1))
        face([(a[0][0], na, a[0][1]), (b[0][0], nb, b[0][1]), (-b[0][0], nb, b[0][1]), (-a[0][0], na, a[0][1])], dark_at, (0, 0, -1))
    # Her two ends, each one face: its outline is the station's.
    for (n, *o), at, out in ((STATIONS[0], uv_stern, (0, -1, 0)), (STATIONS[-1], uv_nose, (0, 1, 0))):
        face([(e, n, h) for e, h in o] + [(-e, n, h) for e, h in reversed(o)], at, out)
    # A nacelle under each side of her waist, on a pylon.
    ei, eo, n0, n1, h0, h1 = NACELLE
    pi, po, pn0, pn1, ph0, ph1 = PYLON
    for s in (1, -1):
        e0, e1 = (ei, eo) if s > 0 else (-eo, -ei)
        # Its picture is on its outer side, and has its stern at the left: from outside her port
        # side her nose is at the left, so there the picture is turned over. Its inner side is dark.
        a, b = (n0, n1) if s > 0 else (n1, n0)
        face([(s * eo, a, h0), (s * eo, b, h0), (s * eo, b, h1), (s * eo, a, h1)], rect("nacelle", flip=s < 0), (s, 0, 0))
        face([(s * ei, b, h0), (s * ei, a, h0), (s * ei, a, h1), (s * ei, b, h1)], rect("dark"), (-s, 0, 0))
        face([(e0, n0, h0), (e1, n0, h0), (e1, n0, h1), (e0, n0, h1)], rect("exhaust"), (0, -1, 0))
        face([(e1, n1, h0), (e0, n1, h0), (e0, n1, h1), (e1, n1, h1)], rect("bussard"), (0, 1, 0))
        face([(e1, n0, h1), (e1, n1, h1), (e0, n1, h1), (e0, n0, h1)], rect("nactop"), (0, 0, 1))
        face([(e0, n1, h0), (e1, n1, h0), (e1, n0, h0), (e0, n0, h0)], rect("dark"), (0, 0, -1))
        p0, p1 = (pi, po) if s > 0 else (-po, -pi)
        box(p0, pn0, p1, pn1, ph0, ph1, "plain", "plain", "plain", "plain")
    e0, n0, e1, n1, h0, h1 = POD
    box(e0, n0, e1, n1, h0, h1, "pod", "podtop", "pod", "pod")
    kit.wound(m, "the hull")
    return m


def emit(m, path, name):
    nv, nf = m.emit(path, name, "TREK_Shuttle.png")
    # meshbuild writes with the platform's line endings; the game reads either.
    return nv, nf


# ------------------------------------------------------------------------------ the engine's files
def write_vehicle():
    """Her vehicle script's skin blocks, one for each livery and state, in SKINS' order. Nothing
    else of that file is this generator's."""
    src = open(VEHICLE, encoding="utf-8").read()
    blocks = "".join("        skin\n        {\n            texture = %s,\n        }\n\n" % skin_name(i) for i in range(len(SKINS)))
    out, n = re.subn(r"(?:        skin\n        \{\n            texture = \w+,\n        \}\n\n)+", lambda _: blocks, src, count=1)
    if n != 1:
        raise SystemExit("trekshuttle_vehicle.txt has no skin block to follow")
    if out != src:
        with open(VEHICLE, "w", encoding="utf-8", newline="\n") as f:
            f.write(out)


def config_skins():
    """C.HullLiveries and C.HullStates, as TREK_Config.lua has them."""
    cfg = open(CONFIG, encoding="utf-8").read()
    out = []
    for key in ("HullLiveries", "HullStates"):
        found = re.search(r"^C\.%s\s*=\s*\{([^}]*)\}" % key, cfg, re.M)
        if not found:
            raise SystemExit("TREK_Config.lua has no C.%s" % key)
        out.append(re.findall(r'"(\w+)"', found.group(1)))
    return out


def build_icon(path, mesh, sheet):
    """Her icon, 64 square: the hull itself, in her first skin, from above her shoulder."""
    pic, _ = kit.shoot([(kit.enh(mesh), mesh.faces, mesh.uvs, np.asarray(sheet))], 256, yaw_deg=145, bg=(0, 0, 0), cull=True)
    a = np.asarray(pic.convert("RGB"), np.int32)
    alpha = np.where(a.sum(axis=2) > 0, 255, 0).astype(np.uint8)
    icon = Image.fromarray(np.dstack([a.astype(np.uint8), alpha]), "RGBA")
    box = icon.getbbox()
    icon = icon.crop(box)
    side = max(icon.size)
    square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    square.paste(icon, ((side - icon.size[0]) // 2, (side - icon.size[1]) // 2))
    square.resize((64, 64), Image.LANCZOS).save(path)


def main():
    for d in ("models_X", "textures", "ui"):
        os.makedirs(os.path.join(MEDIA, d), exist_ok=True)
    os.makedirs(ART, exist_ok=True)
    liveries, states = config_skins()
    if liveries != list(LIVERIES) or states != list(STATES):
        raise SystemExit("C.HullLiveries and C.HullStates are not this file's LIVERIES and STATES, in order")

    world = hull_mesh()
    emit(world, os.path.join(MEDIA, "models_X", "TREK_ShuttleHull.x"), "TREKShuttleHull")
    hull = kit.for_vehicle(hull_mesh())
    nv, nf = emit(hull, os.path.join(MEDIA, "models_X", "TREK_Shuttle.x"), "TREKShuttle")
    xs, ys, zs = zip(*hull.verts)
    size = (max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))
    print("hull: %d vertices, %d faces; %.2f wide, %.2f tall, %.2f long; her lowest point %.2f up" % (nv, nf, size[0], size[1], size[2], min(ys)))
    if abs(max(zs) + min(zs)) > 0.001 or abs(max(xs) + min(xs)) > 0.001 or abs(min(ys)) > 0.001:
        raise SystemExit("the hull is not centred, or does not stand on y = 0")
    if abs(size[0] - HULL_W) > 0.001 or abs(size[2] - HULL_L) > 0.001:
        raise SystemExit("the hull is not HULL_W by HULL_L: the room she is given to land in would be wrong")
    write_vehicle()

    # Every skin, on one page: a livery to a row, a state to a column. Drawn culled, as the
    # engine draws: a face wound the wrong way would be a hole here.
    cell = 440
    page = Image.new("RGB", (len(STATES) * cell, len(LIVERIES) * cell), (28, 30, 36))
    v, frame, sheets = kit.enh(world), None, {}
    for i, (livery, state) in enumerate(SKINS):
        sheet = build_sheet(livery, state)
        sheet.save(os.path.join(MEDIA, "textures", skin_name(i) + ".png"))
        sheets[i] = np.asarray(sheet)
        if i == 0:
            sheet.save(os.path.join(ART, "shuttle_sheet.png"))
            for rel in (os.path.join("ui", "TREK_Shuttle.png"), os.path.join("textures", "Item_TREK_Shuttle.png")):
                build_icon(os.path.join(MEDIA, rel), world, sheet)
        if (livery, state) == ("fleet", "derelict"):
            sheet.save(os.path.join(ART, "shuttle_sheet_derelict.png"))
        pic, frame = kit.shoot([(v, world.faces, world.uvs, sheets[i])], cell, yaw_deg=145, frame=frame, cull=True)
        page.paste(pic, ((i % len(STATES)) * cell, (i // len(STATES)) * cell))
    page.save(os.path.join(ART, "shuttle_skins.png"))

    # Beside a car and a person, from both ends, half a square up as the vehicle carries her;
    # and the four quarters of her close to, worn.
    lifted = v + (0, 0, 0.5)
    scene = [kit.scenery(), (lifted, world.faces, world.uvs, sheets[0])]
    a, frame = kit.shoot(scene, 900, yaw_deg=145, cull=True)
    a.save(os.path.join(ART, "shuttle_a.png"))
    kit.shoot(scene, 900, yaw_deg=-35, frame=frame, cull=True)[0].save(os.path.join(ART, "shuttle_b.png"))
    turn = Image.new("RGB", (4 * 520, 520), (28, 30, 36))
    for i, yaw in enumerate((145, 55, -35, -125)):
        turn.paste(kit.shoot([(v, world.faces, world.uvs, sheets[1])], 520, yaw_deg=yaw, cull=True)[0], (i * 520, 0))
    turn.save(os.path.join(ART, "shuttle_turn.png"))

    import gen_vehicle_assets
    gen_vehicle_assets.main()
    print("%d skins: %s ..." % (len(SKINS), ", ".join(skin_name(i) for i in range(4))))
    print("look at design/art/shuttle/shuttle_skins.png, shuttle_a.png, shuttle_b.png and shuttle_turn.png")
    print("length for the vehicle script's extents: %.2f" % size[2])


if __name__ == "__main__":
    main()
