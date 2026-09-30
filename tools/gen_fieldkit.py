"""The engineer's field kit: five Starfleet tools, the stem bolts and the satchel.

    python tools/gen_fieldkit.py TrekShuttle/42

Writes
    media/models_X/TREK_<Tool>.x                 five tools and a stem bolt
    media/textures/TREK_FieldTools.png           the one texture they share
    media/textures/Item_TREK_<Tool>.png          64x64 icons, rendered from the meshes
    media/textures/clothes/trek/fieldkit.png     the satchel, vanilla's recoloured
    media/textures/Item_TREK_FieldKit.png        its icon, rendered from the worn rig
    media/clothing/clothingItems/TrekFieldKit*.xml  worn, and in either hand
    media/fileGuidTable.xml                      their rows, merged (gen_backpack's rule)
    design/art/fieldkit/fieldkit_sheet.png       everything, and every icon at 64 and 32

**The tools are held the way vanilla's are.** Vanilla's hacksaw and blowtorch
(`models_X/Hacksaw.X`, `Blowtorch.X`, measured) are thin across X, run their
length up +Y from a grip at the origin, and their model blocks carry no hand
attachment, so the engine's default puts them in the fist. These are built
to the same frame; the blades are too, and they hold correctly. Sizes sit in
vanilla's bracket: a screwdriver is ~0.22 long, the hacksaw 0.28.

**What makes each one readable at 32 pixels is its tip.** At icon size the
tools are five grey sticks; the emitter colour is the difference: the sonic
driver blue, the laser cutter phaser orange, the welder cyan, the
hyperspanner its open jaws, the stem bolt driver its T head. The icons are
drawn on the diagonal, as vanilla draws every long thin thing (DEV_GUIDE,
*A blade is its silhouette*).

**The satchel is vanilla's rig in Starfleet colours**, the field pack's route
(tools/gen_backpack.py): the vanilla leather sheet's own shading kept, the
leather made charcoal and the buckles Starfleet grey, and a gold delta on the
flap. Where the flap is was *measured*, not placed by eye: the texels of the
flap's rectangle in the vanilla sheet that face outward (+Z) on the rig give
its world centre (DEV_GUIDE, *Ask the asset which way round it is*).
"""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
from PIL import Image as PILImage

from meshbuild import MeshBuilder
from pngwrite import Image
from preview_model import render
from gen_uniform import surface_map, clothing_guid
from gen_backpack import merge_guid_table, visible_from_behind

TEX = 64
SIDES = 8
PREVIEW_BG = (28, 30, 36)

PZ = r"C:\Program Files (x86)\Steam\steamapps\common\ProjectZomboid"
PACKS = os.path.join(PZ, "media", "models_X", "Skinned", "BackPacks")
VANILLA_SATCHEL = os.path.join(PZ, "media", "textures", "clothes", "bag", "Satchel.png")
SATCHEL_RIGS = ("M_Satchel.X", "F_Satchel.X")
SATCHEL_TEXTURE = "clothes\\trek\\fieldkit"      # as the clothing XML names it
SATCHEL_ITEM = "TrekFieldKit"

# --- the tools' texture ---------------------------------------------------
GRIP = (0, 0, 16, 16)
BODY = (16, 0, 32, 16)
DARK = (32, 0, 48, 16)
GOLD = (48, 0, 64, 16)
BLUE = (0, 16, 16, 32)
ORANGE = (16, 16, 32, 32)
CYAN = (32, 16, 48, 32)
CAP = (48, 16, 64, 32)
PANEL = (0, 32, 64, 48)       # Starfleet grey with an LCARS strip down it

# Gunmetal, not black: a black grip vanished into the inventory's dark grey
# and left each icon a floating grey stub (design/art/fieldkit/fieldkit_icons.png).
C_GRIP = (66, 70, 80)
C_GRIP_RIDGE = (96, 100, 112)
C_BODY = (172, 176, 186)
C_SEAM = (120, 124, 134)
C_DARK = (84, 88, 98)
C_GOLD = (216, 178, 76)       # gen_uniform.BADGE_GOLD: one gold in the mod
C_CAP = (60, 63, 72)
C_LCARS = ((255, 153, 0), (204, 153, 204), (153, 153, 255))
GLOWS = {
    BLUE: ((70, 120, 255), (140, 180, 255), (230, 240, 255)),
    ORANGE: ((255, 110, 30), (255, 170, 70), (255, 235, 200)),
    CYAN: ((40, 200, 230), (120, 235, 250), (225, 252, 255)),
}


def paint():
    img = Image(TEX, TEX, C_BODY + (255,))
    img.rect(*GRIP, C_GRIP + (255,))
    x0, y0, x1, y1 = GRIP
    for y in range(y0 + 1, y1, 3):            # the grip's ridges
        img.rect(x0, y, x1, y + 1, C_GRIP_RIDGE + (255,))
    img.rect(*BODY, C_BODY + (255,))
    img.rect(BODY[0], 7, BODY[2], 8, C_SEAM + (255,))
    img.rect(*DARK, C_DARK + (255,))
    img.rect(*GOLD, C_GOLD + (255,))
    img.rect(*CAP, C_CAP + (255,))
    # An emitter is a line of light: hot in the middle, its colour at the edge.
    for region, (edge, mid, hot) in GLOWS.items():
        rx0, ry0, rx1, ry1 = region
        c = (ry0 + ry1) / 2
        for y in range(ry0, ry1):
            d = abs(y + 0.5 - c) / ((ry1 - ry0) / 2)
            col = hot if d < 0.3 else mid if d < 0.65 else edge
            img.rect(rx0, y, rx1, y + 1, col + (255,))
    px0, py0, px1, py1 = PANEL
    img.rect(px0, py0, px1, py1, C_BODY + (255,))
    for i, col in enumerate(C_LCARS):         # three LCARS blocks across it
        img.rect(px0 + 8 + i * 18, py0 + 5, px0 + 22 + i * 18, py0 + 11, col + (255,))
    return img


def inset(region):
    """A texel in from every edge: the sampler reads past a triangle's edge,
    and an emitter next to a grey cap came out speckled (the sentry)."""
    x0, y0, x1, y1 = region
    return (x0 + 1, y0 + 1, x1 - 1, y1 - 1)


class Tool:
    """One tool, built in (east, north, height) with height the model's Y:
    the grip at the origin, the length up it."""

    def __init__(self):
        self.mb = MeshBuilder(TEX, TEX, up_axis="y")

    def quad(self, p0, p1, p2, p3, region, normal):
        P = self.mb.place
        a, b, c = (np.array(p) for p in (p0, p1, p2))
        if np.dot(np.cross(b - a, c - a), normal) < 0:
            p0, p1, p2, p3 = p1, p0, p3, p2
        self.mb.quad(P(*p0), P(*p1), P(*p2), P(*p3), inset(region), P(*normal))

    def prism(self, r0, r1, h0, h1, side, top=CAP, bottom=CAP):
        def ring(r, h, i):
            a = 2 * math.pi * (i + 0.5) / SIDES
            return (r * math.cos(a), r * math.sin(a), h)
        for i in range(SIDES):
            a0, a1 = ring(r0, h0, i), ring(r0, h0, i + 1)
            b0, b1 = ring(r1, h1, i), ring(r1, h1, i + 1)
            if r1 == 0:
                b0 = b1 = (0.0, 0.0, h1)
            mid = 2 * math.pi * (i + 1) / SIDES
            n = (math.cos(mid) * (h1 - h0), math.sin(mid) * (h1 - h0), r0 - r1)
            self.quad(a0, a1, b1, b0, side, n)
        for cap, h, r, up in ((top, h1, r1, 1), (bottom, h0, r0, -1)):
            if cap is None or r == 0:
                continue
            for i in range(SIDES):
                p0, p1 = ring(r, h, i), ring(r, h, i + 1)
                self.quad((0.0, 0.0, h), p0, p1, (0.0, 0.0, h), cap, (0, 0, up))

    def cuboid(self, x0, x1, n0, n1, h0, h1, side, ends=CAP):
        c = [(x, n, h) for h in (h0, h1) for n in (n0, n1) for x in (x0, x1)]
        faces = (((0, 1, 5, 4), (0, -1, 0), side), ((2, 3, 7, 6), (0, 1, 0), side),
                 ((0, 2, 6, 4), (-1, 0, 0), side), ((1, 3, 7, 5), (1, 0, 0), side),
                 ((4, 5, 7, 6), (0, 0, 1), ends), ((0, 1, 3, 2), (0, 0, -1), ends))
        for idx, normal, region in faces:
            self.quad(*(c[i] for i in idx), region, normal)


def grip(t, top=0.085):
    """Every tool's handle: the ridged black grip and a gold collar."""
    t.prism(0.012, 0.012, 0.0, top, GRIP)
    t.prism(0.0135, 0.0135, top, top + 0.010, GOLD)


def sonic_driver():
    t = Tool()
    grip(t)
    t.prism(0.010, 0.010, 0.095, 0.165, BODY)
    t.prism(0.008, 0.008, 0.165, 0.180, DARK)
    t.prism(0.006, 0.006, 0.180, 0.205, BLUE)
    t.prism(0.006, 0.0, 0.205, 0.215, BLUE)
    return t


def hyperspanner():
    t = Tool()
    grip(t, 0.090)
    t.cuboid(-0.017, 0.017, -0.009, 0.009, 0.100, 0.220, PANEL)
    t.cuboid(-0.020, 0.020, -0.011, 0.011, 0.220, 0.240, DARK)
    for x0, x1 in ((-0.020, -0.008), (0.008, 0.020)):    # the open jaws
        t.cuboid(x0, x1, -0.008, 0.008, 0.240, 0.285, DARK)
    t.cuboid(-0.008, 0.008, -0.004, 0.004, 0.240, 0.247, BLUE)
    return t


def stem_bolt_driver():
    t = Tool()
    grip(t, 0.140)
    t.prism(0.011, 0.011, 0.150, 0.170, BODY)
    t.cuboid(-0.045, 0.045, -0.017, 0.017, 0.170, 0.215, PANEL)   # the T head
    t.cuboid(0.045, 0.056, -0.013, 0.013, 0.175, 0.210, GOLD)     # the driving face
    t.cuboid(-0.052, -0.045, -0.012, 0.012, 0.178, 0.207, DARK)
    return t


def laser_cutter():
    t = Tool()
    grip(t)
    t.prism(0.016, 0.013, 0.095, 0.180, BODY)
    t.prism(0.007, 0.007, 0.180, 0.225, DARK)
    t.prism(0.0065, 0.0065, 0.225, 0.240, ORANGE)
    t.prism(0.0065, 0.0, 0.240, 0.248, ORANGE)
    return t


def laser_welder():
    t = Tool()
    grip(t)
    t.cuboid(-0.022, 0.022, -0.019, 0.019, 0.095, 0.175, PANEL)
    t.prism(0.013, 0.013, 0.175, 0.190, DARK)
    t.prism(0.009, 0.007, 0.190, 0.230, DARK)
    t.prism(0.011, 0.011, 0.230, 0.240, CYAN)
    t.prism(0.007, 0.0, 0.240, 0.250, CYAN)
    return t


def stem_bolt():
    """One self-sealing stem bolt: a gold head and a grey shank, held like a
    nail. Only the icon and the world model need it."""
    t = Tool()
    t.prism(0.012, 0.012, 0.0, 0.008, GOLD)
    t.prism(0.004, 0.004, 0.008, 0.020, BODY)
    t.prism(0.0048, 0.0048, 0.020, 0.024, GOLD)      # the self-sealing collar
    t.prism(0.004, 0.004, 0.024, 0.046, BODY)
    t.prism(0.004, 0.0015, 0.046, 0.052, BODY)
    return t


TOOLS = (
    ("SonicDriver", sonic_driver),
    ("Hyperspanner", hyperspanner),
    ("StemBoltDriver", stem_bolt_driver),
    ("LaserCutter", laser_cutter),
    ("LaserWelder", laser_welder),
    ("StemBolt", stem_bolt),
)


ICON_GAIN = 1.35        # the phaser's rule: an icon brighter than the model
OUTLINE = (18, 18, 22)  # and a one-pixel dark outline, like its neighbours


def trim_icon(im, icon_path, size=64, floor=None, gain=ICON_GAIN):
    """gen_padd.icon_from's recipe (exact key on the backdrop, a square crop
    with a small margin, alpha-weighted box filter), with a floor that fits a
    thin tool: a screwdriver on the diagonal honestly covers a fifth of its
    frame, which icon_from, written for a tablet, refuses."""
    im = im.convert("RGB")
    w, h = im.size
    px = im.load()
    xs = [x for y in range(h) for x in range(w) if px[x, y] != PREVIEW_BG]
    ys = [y for y in range(h) for x in range(w) if px[x, y] != PREVIEW_BG]
    if not xs:
        raise SystemExit(f"{icon_path}: the render is empty")
    side = int((max(max(xs) - min(xs), max(ys) - min(ys)) + 1) * 1.06) + 2
    left = (max(xs) + min(xs)) // 2 - side // 2
    top = (max(ys) + min(ys)) // 2 - side // 2
    out = PILImage.new("RGBA", (size, size), (0, 0, 0, 0))
    po = out.load()
    step = side / size
    for oy in range(size):
        for ox in range(size):
            r = g = b = a = n = 0
            for sy in range(top + int(oy * step), top + int((oy + 1) * step)):
                for sx in range(left + int(ox * step), left + int((ox + 1) * step)):
                    n += 1
                    if 0 <= sx < w and 0 <= sy < h and px[sx, sy] != PREVIEW_BG:
                        c = px[sx, sy]
                        r, g, b, a = r + c[0], g + c[1], b + c[2], a + 1
            if a:
                po[ox, oy] = tuple(min(255, int(c / a * gain)) for c in (r, g, b))                     + (255 * a // n,)
    solid = {(x, y) for y in range(size) for x in range(size) if po[x, y][3] > 96}
    for y in range(size):
        for x in range(size):
            if (x, y) in solid:
                continue
            if any((x + dx, y + dy) in solid for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                po[x, y] = OUTLINE + (255,)
    covered = sum(1 for y in range(size) for x in range(size) if po[x, y][3] > 0)
    if covered < (floor if floor is not None else size * size // 10):
        raise SystemExit(f"{icon_path}: only {covered} of {size * size} pixels came "
                         f"out; the render or the key is wrong")
    out.save(icon_path)
    return covered


def diagonal_icon(x_path, tex_path, icon_path, scratch, yaw=145):
    """Rendered three-quarter on (edge-on, the driver's head and the
    spanner's jaws vanished), turned 45 degrees and trimmed. Nearest-
    neighbour turning keeps the backdrop an exact colour, so the exact key
    still finds it."""
    side = os.path.join(scratch, "_fk_side.png")
    render(x_path, tex_path, side, size=384, yaw_deg=yaw)
    with PILImage.open(side) as f:
        im = f.convert("RGB")
    os.remove(side)
    im = im.rotate(-45, resample=PILImage.NEAREST, expand=True, fillcolor=PREVIEW_BG)
    return trim_icon(im, icon_path)


def bolts_icon(x_path, tex_path, icon_path, scratch):
    """Three bolts, as vanilla's nails are a handful: one render, laid down
    three times at different turns and places, then trimmed."""
    one = os.path.join(scratch, "_fk_bolt.png")
    render(x_path, tex_path, one, size=200, yaw_deg=145)
    with PILImage.open(one) as f:
        bolt = f.convert("RGB")
    os.remove(one)
    canvas = PILImage.new("RGB", (420, 420), PREVIEW_BG)
    for turn, (x, y) in ((-50, (40, 150)), (-20, (130, 60)), (-80, (170, 190))):
        b = bolt.rotate(turn, resample=PILImage.NEAREST, expand=True, fillcolor=PREVIEW_BG)
        mask = PILImage.eval(b.convert("L"), lambda v: 0)
        bp, mp = b.load(), mask.load()
        for yy in range(b.size[1]):
            for xx in range(b.size[0]):
                if bp[xx, yy] != PREVIEW_BG:
                    mp[xx, yy] = 255
        canvas.paste(b, (x, y), mask)
    return trim_icon(canvas, icon_path)


# --- the satchel ----------------------------------------------------------
FABRIC = (52, 54, 63)         # the field pack's charcoal (gen_backpack)
TRIM = (122, 126, 137)
RIM = (38, 30, 14)
# Where the badge goes, as a rectangle of the vanilla sheet: the front of the
# flap between its two buckle straps. Read off design/art/fieldkit/
# satchel_faces.png, the sheet with every texel that faces outward (+Z) on
# each rig tinted red: the lighter lid above it faces *up*, not out, and a
# badge there would be seen only from overhead.
FLAP_UV = (82, 118, 134, 150)
DELTA_TEX_W = 22      # texels; the flap is ~134 by 42 of them
DELTA_TEX_H = 26
RIM_SCALE = 1.25


def in_delta(u, v, scale=1.0):
    """gen_backpack's arrowhead in unit coordinates: u -1..1 across, v 0 at
    the base and 1 at the apex; grown by `scale` about its centre."""
    u = u / scale
    v = (v - 0.5) / scale + 0.5
    if v < 0.0 or v > 1.0 or abs(u) > 1.0 or abs(u) > 1.0 - v:
        return False
    return v >= 0.42 * (1.0 - abs(u)) ** 1.6


def recolour_satchel(src):
    """Leather to charcoal, buckles to Starfleet grey, each keeping its own
    shading. The buckles are the unsaturated texels; everything else is hide."""
    px = src.load()
    w, h = src.size
    hide, metal = [], []
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a == 0:
                continue
            lum = 0.30 * r + 0.59 * g + 0.11 * b
            (hide if r > b + 25 else metal).append(lum)
    if len(hide) < 5000 or len(metal) < 50:
        raise SystemExit(f"the satchel sheet split into {len(hide)} hide and "
                         f"{len(metal)} buckle texels; the colour test no longer "
                         f"matches it, and the bag would come out one flat colour")

    def ref(values):
        top = sorted(values)[len(values) // 2:]
        return sum(top) / len(top)
    rh, rm = ref(hide), ref(metal)
    out = PILImage.new("RGBA", (w, h), (0, 0, 0, 0))
    po = out.load()
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            lum = 0.30 * r + 0.59 * g + 0.11 * b
            base, f = (FABRIC, lum / rh) if r > b + 25 else (TRIM, lum / rm)
            po[x, y] = tuple(max(0, min(255, int(round(c * f)))) for c in base) + (a,)
    return out


def flap_texels(rig, size):
    """The flap's outward-facing texels on one rig, with their world spots."""
    pos, covered = surface_map(os.path.join(PACKS, rig), size, size)
    if sum(covered) < 5000:
        raise SystemExit(f"{rig}: only {sum(covered)} texels covered; the UVs are "
                         f"not being read, so the flap cannot be found")
    vis = visible_from_behind(pos, covered)
    x0, y0, x1, y1 = FLAP_UV
    out = {(x, y): pos[y * size + x] for y in range(y0, y1) for x in range(x0, x1)
           if vis[y * size + x]}
    if len(out) < 200:
        raise SystemExit(f"{rig}: {len(out)} outward flap texels; FLAP_UV no longer "
                         f"covers the flap, and the delta would land anywhere")
    return out


def flap_badge(size):
    """{(x, y): 'gold' | 'rim'} in the texture, the same texels on both bodies.

    The flap is one flat panel in the sheet, so the badge is drawn there, in
    texture space, which makes it identical on both rigs by construction. What
    the rig is asked is which way is up: whether world height rises with the
    sheet's v or against it (an atlas owes nothing to the world). And the
    badge must land on texels that face outward on *both* bodies.
    """
    male = flap_texels(SATCHEL_RIGS[0], size)
    female = flap_texels(SATCHEL_RIGS[1], size)
    both = set(male) & set(female)
    xs = [x for x, _ in both]
    ys = [y for _, y in both]
    cx, cy = (min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0
    # Up, from the male rig: the correlation of texel v with world height.
    mv = sum(y for _, y in male) / len(male)
    mh = sum(p[1] for p in male.values()) / len(male)
    cov = sum((y - mv) * (p[1] - mh) for (_, y), p in male.items())
    up = -1 if cov > 0 else 1            # +1: world up is toward smaller v
    hw, h = DELTA_TEX_W / 2.0, DELTA_TEX_H
    out = {}
    for y in range(int(cy - h), int(cy + h) + 1):
        for x in range(int(cx - hw * RIM_SCALE) - 1, int(cx + hw * RIM_SCALE) + 2):
            u = (x + 0.5 - cx) / hw
            v = 0.5 + up * (cy - (y + 0.5)) / h
            if in_delta(u, v):
                out[(x, y)] = "gold"
            elif in_delta(u, v, RIM_SCALE):
                out[(x, y)] = "rim"
    gold = [k for k, t in out.items() if t == "gold"]
    shown = sum(1 for k in gold if k in both) / float(len(gold) or 1)
    print(f"  satchel: delta {len(gold)} texels at {cx:.0f},{cy:.0f} in the sheet, "
          f"up is {'-' if up > 0 else '+'}v, {shown * 100:.0f}% facing out on both bodies")
    if len(gold) < 40 or shown < 0.9:
        raise SystemExit("the delta does not sit on the flap's outer face on both bodies")
    return out


def paint_satchel(tex_out):
    src = PILImage.open(VANILLA_SATCHEL).convert("RGBA")
    img = recolour_satchel(src)
    po = img.load()
    for (x, y), kind in flap_badge(src.size[0]).items():
        po[x, y] = (C_GOLD if kind == "gold" else RIM) + (po[x, y][3],)
    img.save(tex_out)


SATCHEL_CLOTHING = (
    (SATCHEL_ITEM, "media\\models_X\\Skinned\\BackPacks\\M_Satchel.X",
     "media\\models_X\\Skinned\\BackPacks\\F_Satchel.X"),
    (SATCHEL_ITEM + "_RHand", "media\\models_X\\Skinned\\BackPacks\\Satchel_RHand.X",
     "media\\models_X\\Skinned\\BackPacks\\Satchel_RHand.X"),
    (SATCHEL_ITEM + "_LHand", "media\\models_X\\Skinned\\BackPacks\\Satchel_LHand.X",
     "media\\models_X\\Skinned\\BackPacks\\Satchel_LHand.X"),
)


def write_satchel_clothing(root):
    out_dir = os.path.join(root, "media", "clothing", "clothingItems")
    os.makedirs(out_dir, exist_ok=True)
    rows = []
    for stem, male, female in SATCHEL_CLOTHING:
        guid = clothing_guid(stem)
        lines = ['<?xml version="1.0" encoding="utf-8"?>',
                 "<clothingItem>",
                 f"\t<m_MaleModel>{male}</m_MaleModel>",
                 f"\t<m_FemaleModel>{female}</m_FemaleModel>",
                 f"\t<m_GUID>{guid}</m_GUID>",
                 "\t<m_Static>false</m_Static>",
                 "\t<m_AllowRandomHue>false</m_AllowRandomHue>",
                 "\t<m_AllowRandomTint>false</m_AllowRandomTint>",
                 "\t<m_AttachBone></m_AttachBone>",
                 "\t<m_MasksFolder>none</m_MasksFolder>",
                 f"\t<textureChoices>{SATCHEL_TEXTURE}</textureChoices>",
                 "</clothingItem>"]
        with open(os.path.join(out_dir, stem + ".xml"), "w",
                  encoding="utf-8", newline="\r\n") as fh:
            fh.write("\n".join(lines) + "\n")
        rows.append((f"media/clothing/clothingItems/{stem}.xml", guid))
    merge_guid_table(root, rows)
    print(f"  {len(rows)} clothing XMLs and their GUID rows")


def satchel_icon(tex, out_path, scratch):
    big = os.path.join(scratch, "_fk_satchel.png")
    render(os.path.join(PACKS, SATCHEL_RIGS[0]), tex, big, size=384, yaw_deg=180)
    with PILImage.open(big) as f:
        im = f.convert("RGB")
    os.remove(big)
    # The strap would be most of the icon and the bag a small box under it.
    # Its rows are narrow and the bag's are wide, so everything above the
    # first row at least 40% as wide as the widest is blanked out.
    px = im.load()
    w, h = im.size
    widths = [sum(1 for x in range(w) if px[x, y] != PREVIEW_BG) for y in range(h)]
    top = next(y for y in range(h) if widths[y] >= 0.4 * max(widths))
    for y in range(top):
        for x in range(w):
            px[x, y] = PREVIEW_BG
    # Charcoal is right on the body and too dark for an icon on dark grey.
    return trim_icon(im, out_path, gain=1.9)


# --- the sheet ------------------------------------------------------------
def sheet(renders, icons, art):
    cell, pad = 200, 6
    n = len(renders)
    W = PILImage.new("RGB", (pad + n * (cell + pad), pad + cell + 120), PREVIEW_BG)
    for i, p in enumerate(renders):
        W.paste(PILImage.open(p).convert("RGB").resize((cell, cell)), (pad + i * (cell + pad), pad))
    panel = (39, 39, 39)
    for i, p in enumerate(icons):
        ic = PILImage.open(p).convert("RGBA")
        for size, dy in ((64, 0), (32, 70)):
            bg = PILImage.new("RGBA", (size, size), panel + (255,))
            bg.alpha_composite(ic.resize((size, size), PILImage.BOX))
            W.paste(bg.convert("RGB"), (pad + i * (cell + pad) + 20, pad + cell + 10 + dy))
    out = os.path.join(art, "fieldkit_sheet.png")
    W.save(out)
    print("  sheet", out)


def build(root, scratch):
    media = os.path.join(root, "media")
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    art = os.path.join(here, "design", "art", "fieldkit")
    for d in (art, scratch, os.path.join(media, "textures", "clothes", "trek")):
        os.makedirs(d, exist_ok=True)
    tex_path = os.path.join(media, "textures", "TREK_FieldTools.png")
    paint().save(tex_path)
    renders, icons = [], []
    for name, make in TOOLS:
        t = make()
        x_path = os.path.join(media, "models_X", f"TREK_{name}.x")
        nv, nf = t.mb.emit(x_path, f"TREK_{name}", "TREK_FieldTools.png")
        ys = [v[1] for v in t.mb.verts]
        xs = [v[0] for v in t.mb.verts]
        print(f"  TREK_{name}: {nf} faces, {max(ys) - min(ys):.3f} long, "
              f"{max(xs) - min(xs):.3f} across")
        icon_path = os.path.join(media, "textures", f"Item_TREK_{name}.png")
        if name == "StemBolt":
            covered = bolts_icon(x_path, tex_path, icon_path, scratch)
        else:
            covered = diagonal_icon(x_path, tex_path, icon_path, scratch)
        if covered < 300:
            raise SystemExit(f"{icon_path}: {covered} pixels covered; the icon is empty")
        icons.append(icon_path)
        r = os.path.join(scratch, f"_fk_{name}.png")
        render(x_path, tex_path, r, size=256, yaw_deg=145)
        renders.append(r)

    sat_tex = os.path.join(media, "textures", "clothes", "trek", "fieldkit.png")
    paint_satchel(sat_tex)
    sat_icon = os.path.join(media, "textures", "Item_TREK_FieldKit.png")
    print(f"  satchel icon: {satchel_icon(sat_tex, sat_icon, scratch)} pixels covered")
    icons.append(sat_icon)
    r = os.path.join(scratch, "_fk_satchel_view.png")
    render(os.path.join(PACKS, SATCHEL_RIGS[1]), sat_tex, r, size=256, yaw_deg=160)
    renders.append(r)
    write_satchel_clothing(root)
    sheet(renders, icons, art)
    for p in renders:
        os.remove(p)


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else os.path.join("TrekShuttle", "42")
    scratch = os.environ.get("TREK_SCRATCH") or os.path.join(root, "_scratch")
    print("field kit:")
    build(root, scratch)
