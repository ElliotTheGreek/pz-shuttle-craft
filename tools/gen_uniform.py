"""Generates the Starfleet uniforms: textures, icons and the contact sheet.

    python tools/gen_uniform.py TrekShuttle/42

Two garments, three divisions each, on **vanilla rigs**. Nothing here is
rigged, skinned or animated by this project, and that is the whole design:

  duty uniform   skinned\\clothes\\bob_boilersuit / kate_boilersuit
  dress uniform  skinned\\clothes\\bob_judegsrobe / kate_judegsrobe

Of the 1,795 clothing items build 42 ships, 597 have no mesh at all and the
rest share a small pool of rigs -- 38 items ride `bob_trousers`, 7 ride
`bob_boilersuit`. A garment is an item script, a nine-line clothing XML, a
GUID row and a 256x256 PNG. So a uniform is a **texture**, and the hard part
of ROADMAP2 section 1.4 does not exist.

Why the texture is painted from the mesh's own UVs
--------------------------------------------------
The same reason `gen_emh.py` bands the hologram in world height: these atlases
are auto-packed, so a rectangle in texture space is not a shape on the
garment. Painting a chest panel by eye in a 256px sheet puts stripes across a
sleeve and half a trouser leg. Every texel here is given the **world position**
of the surface it lands on, and every region, seam and the combadge is decided
from that. The EMH's scanlines came out as wood grain the one time this was
done the obvious way.

What the geometry says
----------------------
Both rigs are bind pose, Y up, X the arm span, Z depth, and they profile
identically: from the hem up to 0.80 of the model's height the silhouette is
under 0.15 wide -- body and legs -- and above 0.80 it reaches 0.375, which is
the arms out sideways. That single number is what separates a sleeve from a
shoulder, and it is measured rather than assumed.

**Front is negative Z.** Rendered at yaw 0 the boilersuit shows its zip and
chest pockets and the robe shows its V-wrap and yoke seam; at yaw 0 the near
surface is the one with the smaller Z. The combadge sits on the wearer's left
breast and would be invisible on the wrong face until somebody looked in game,
so the convention is written down here rather than remembered.

Both sexes share one texture -- vanilla points `textureChoices` at a single
path for both models -- so the region map is built from **both** rigs and they
have to agree. `--check` reports the disagreement; a texture that is right for
one body and wrong for the other is exactly the failure this mod keeps
meeting, and it would only ever show on a character nobody happened to make.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pngwrite import Image
from preview_model import parse_x, read_png_rgba, render

PZ = r"C:\Program Files (x86)\Steam\steamapps\common\ProjectZomboid"
RIGS = os.path.join(PZ, "media", "models_X", "Skinned", "Clothes")

SIZE = 256           # what every vanilla clothing texture is
ICON = 64            # nothing here has an AttachmentType, so 64 is right

# --- the divisions ------------------------------------------------------
# Command red, operations gold, science teal. Deliberately deep rather than
# bright: these are read at about forty pixels tall against grass and asphalt,
# and a saturated primary reads as a hazard vest.
DIVISIONS = {
    "Command":    (139, 30, 38),
    "Operations": (188, 142, 40),
    "Science":    (34, 108, 148),
}

# Not pure black: at the size a character is drawn, a true black garment
# loses its own folds against the deck and against night. The same reasoning
# as gen_emh.py's FLOOR.
BLACK     = (31, 31, 37)      # the uniform's dark half
COLLAR    = (19, 19, 24)      # collar band, a shade under the black
UNDERSHIRT = (58, 60, 68)     # the grey showing at the throat
PIPING    = (96, 99, 108)     # the thin seam between panels
BADGE_GOLD = (216, 178, 76)
BADGE_SILVER = (206, 212, 222)

# Where the arms start. Measured: below this the rigs are under 0.15 across
# and above it they reach 0.375, which is the T-pose.
ARM_X = 0.16

# The preview renderer's flat backdrop, keyed by exact match for the icon.
# key_icon.py's colour ramp is wrong here for the reason gen_emh.py gives:
# a ramp eats anything near the backdrop, and these are dark garments.
PREVIEW_BG = (28, 30, 36)


def lerp(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def shade(colour, f):
    return tuple(max(0, min(255, int(round(c * f)))) for c in colour)


# ---------------------------------------------------------------------------
# The mesh, in texture space
# ---------------------------------------------------------------------------
def surface_map(mesh, w, h):
    """Every texel's world position on the garment, and whether one lands there.

    Each triangle is rasterised into texture space and its vertices' positions
    interpolated across it. This is the only honest way to ask "where on the
    *garment* is this texel", which is the question every line below asks.
    """
    verts, faces, uvs = parse_x(mesh)
    pos = [(0.0, 0.0, 0.0)] * (w * h)
    covered = bytearray(w * h)

    for (ia, ib, ic) in faces:
        pts = []
        for i in (ia, ib, ic):
            u, v = uvs[i]
            pts.append((u * w, v * h, verts[i]))
        (ax, ay, pa), (bx, by, pb), (cx, cy, pc) = pts
        minx = max(0, int(min(ax, bx, cx)))
        maxx = min(w - 1, int(max(ax, bx, cx)) + 1)
        miny = max(0, int(min(ay, by, cy)))
        maxy = min(h - 1, int(max(ay, by, cy)) + 1)
        d = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(d) < 1e-12:
            continue
        for py in range(miny, maxy + 1):
            for px in range(minx, maxx + 1):
                l1 = ((by - cy) * (px - cx) + (cx - bx) * (py - cy)) / d
                l2 = ((cy - ay) * (px - cx) + (ax - cx) * (py - cy)) / d
                l3 = 1.0 - l1 - l2
                # A texel of slack, so the gutter between islands is painted
                # with the island beside it rather than left as a bright seam.
                if l1 < -0.05 or l2 < -0.05 or l3 < -0.05:
                    continue
                k = py * w + px
                pos[k] = (l1 * pa[0] + l2 * pb[0] + l3 * pc[0],
                          l1 * pa[1] + l2 * pb[1] + l3 * pc[1],
                          l1 * pa[2] + l2 * pb[2] + l3 * pc[2])
                covered[k] = 1
    return pos, covered


def merge_maps(meshes, w, h):
    """One surface map from several rigs, and the per-rig maps to check it.

    Male and female share a single texture, so a texel's *meaning* has to be
    the same on both bodies. Where only one rig covers a texel that rig
    decides it; where both do they are averaged.

    The first version of this gated on the raw distance between the two rigs'
    positions, and it failed the boilersuit at 0.077 -- which turned out to be
    the collar sitting five centimetres off-centre on Bob and centred on Kate.
    That is two bodies of different shape sharing one layout, which is what
    vanilla ships, and the guard was measuring millimetres when the question
    is **which panel**. See `region_disagreement`, and DEV_GUIDE's *A guard is
    only as good as the goal it was written from*.
    """
    w_h = w * h
    acc = [(0.0, 0.0, 0.0)] * w_h
    count = [0] * w_h
    maps = [surface_map(m, w, h) for m in meshes]
    for pos, covered in maps:
        for k in range(w_h):
            if not covered[k]:
                continue
            if count[k]:
                a, b = acc[k], pos[k]
                acc[k] = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2)
            else:
                acc[k] = pos[k]
            count[k] += 1
    covered = bytearray(1 if c else 0 for c in count)
    return acc, covered, maps


def region_disagreement(garment, maps):
    """How often the two rigs put a shared texel in different panels.

    This is the failure that matters: a texel painted as a sleeve on one body
    and as a trouser leg on the other is a scrambled uniform on whichever
    character the author did not happen to make. Body shape moving a seam by a
    centimetre is not.

    Each rig is measured against *its own* height, because every threshold in
    this file is a fraction of the model rather than an absolute.
    """
    labelled = []
    for pos, covered in maps:
        y0, y1, _ = extents(pos, covered)
        labelled.append(([region_of(garment, p, y0, y1) for p in pos], covered))
    shared = differ = 0
    (la, ca), (lb, cb) = labelled[0], labelled[1]
    for k in range(len(ca)):
        if not (ca[k] and cb[k]):
            continue
        shared += 1
        if la[k] != lb[k]:
            differ += 1
    return differ, shared


def extents(pos, covered):
    ys = [pos[k][1] for k in range(len(covered)) if covered[k]]
    zs = [pos[k][2] for k in range(len(covered)) if covered[k]]
    return min(ys), max(ys), (min(zs) + max(zs)) / 2.0


# ---------------------------------------------------------------------------
# The garments
# ---------------------------------------------------------------------------
class Garment:
    """A recipe for painting one rig.

    `bands` are fractions of the model's own height, bottom to top, so the
    same recipe works on a robe that reaches the floor and a jumpsuit that
    stops at the ankle.
    """

    def __init__(self, key, rigs, lower_top, torso_top, badge_h, name):
        self.key = key
        self.rigs = rigs
        self.lower_top = lower_top    # hem .. here is legs or skirt
        self.torso_top = torso_top    # .. here is the body
        self.badge_h = badge_h        # where the combadge sits
        self.name = name


DUTY = Garment(
    "duty",
    ["Bob_BoilerSuit.X", "Kate_BoilerSuit.x"],
    lower_top=0.46, torso_top=0.80, badge_h=0.755,
    name="duty uniform")

DRESS = Garment(
    "dress",
    ["Bob_JudegsRobe.x", "Kate_JudegsRobe.x"],
    lower_top=0.55, torso_top=0.80, badge_h=0.760,
    name="dress uniform")


def region_of(garment, p, y0, y1):
    """Which panel of the garment this point belongs to."""
    hn = (p[1] - y0) / (y1 - y0) if y1 > y0 else 0.0
    if hn > garment.torso_top:
        return "sleeve" if abs(p[0]) > ARM_X else "yoke"
    if hn > garment.lower_top:
        return "torso"
    return "lower"


def source_mean(src, covered):
    """The source texture's own mean luminance over the texels that matter.

    Centring `cloth_detail` on mid grey works for the boilersuit and does
    nothing at all for the judge's robe, which is black: every texel sits far
    below 0.5, every multiplier pins to the bottom of the clamp, and the skirt
    comes out a flat slab with no folds in it. Normalising to the source's own
    mean gives the same relative fold detail whatever its overall value.
    """
    if src is None:
        return 0.5
    total, n = 0.0, 0
    for k in range(len(covered)):
        if not covered[k]:
            continue
        i = k * 4
        total += (0.299 * src[i] + 0.587 * src[i + 1] + 0.114 * src[i + 2]) / 255.0
        n += 1
    return (total / n) if n else 0.5


def cloth_detail(src, k, mean):
    """A fold multiplier borrowed from the vanilla texture this rig was cut for.

    The rigs are unwrapped for garments that already have creases, seams and
    shading painted in the right places. Throwing that away gives a uniform
    that reads as a flat sticker, so the source's luminance is reused -- but
    **hard-clamped**, because at full strength the flight suit's zip, pockets
    and squadron patch come through as ghosts of somebody else's garment.
    """
    if src is None:
        return 1.0
    i = k * 4
    r, g, b = src[i], src[i + 1], src[i + 2]
    lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255.0
    return max(0.86, min(1.14, 1.0 + (lum - mean) * 0.55))


def paint(garment, colour, out_path, source_texture=None, regions_path=None):
    """Writes one 256x256 uniform texture, and reports what it covered.

    Returns the texel counts per region. A region that came out empty means
    the thresholds no longer match the rig -- which would otherwise ship as a
    uniform with, say, no sleeves, and look entirely deliberate.
    """
    meshes = [os.path.join(RIGS, r) for r in garment.rigs]
    for m in meshes:
        if not os.path.isfile(m):
            raise SystemExit(f"rig not found: {m}")
    pos, covered, maps = merge_maps(meshes, SIZE, SIZE)
    y0, y1, zmid = extents(pos, covered)
    differ, shared = region_disagreement(garment, maps)

    src = None
    if source_texture and os.path.isfile(source_texture):
        sw, sh, src_px = read_png_rgba(source_texture)
        if (sw, sh) == (SIZE, SIZE):
            src = src_px
    src_mean = source_mean(src, covered)

    img = Image(SIZE, SIZE, (0, 0, 0, 0))
    dbg = Image(SIZE, SIZE, (0, 0, 0, 0)) if regions_path else None
    counts = {"sleeve": 0, "yoke": 0, "torso": 0, "lower": 0, "badge": 0}

    DEBUG_COLOURS = {"sleeve": (230, 80, 80, 255), "yoke": (80, 200, 120, 255),
                     "torso": (90, 140, 240, 255), "lower": (235, 200, 70, 255)}

    span = y1 - y0
    badge_y = y0 + span * garment.badge_h
    # About six centimetres on a figure this size. Nudged up for legibility:
    # the character is drawn some forty pixels tall and a true-scale badge is
    # two of them.
    badge_rx, badge_ry = 0.031, 0.021

    for y in range(SIZE):
        for x in range(SIZE):
            k = y * SIZE + x
            if not covered[k]:
                continue
            p = pos[k]
            reg = region_of(garment, p, y0, y1)
            counts[reg] += 1
            hn = (p[1] - y0) / span if span else 0.0

            if dbg:
                dbg.set(x, y, DEBUG_COLOURS[reg])

            if garment.key == "duty":
                base = _duty_colour(reg, hn, p, colour, garment)
            else:
                base = _dress_colour(reg, hn, p, colour, garment)

            # The combadge: world space, front face, wearer's **left**.
            #
            # Which x that is was derived from the geometry first -- forward
            # -Z, up +Y, so left = up x forward = -X -- and the render put the
            # badge on the wrong breast. The rigs carry a named skeleton, and
            # it answers the question outright: every `Bip01_L_*` bone weights
            # vertices at **positive** x (L_Hand +0.369, R_Hand -0.369). So
            # ask the rig rather than reason about handedness.
            if p[2] < zmid and p[0] > 0:
                dx = (p[0] - 0.055) / badge_rx
                dy = (p[1] - badge_y) / badge_ry
                d = math.hypot(dx, dy)
                if d < 1.0:
                    base = BADGE_GOLD if d > 0.52 else BADGE_SILVER
                    counts["badge"] += 1

            f = cloth_detail(src, k, src_mean)
            # A touch darker toward the hem of each panel, which is what stops
            # a flat fill reading as plastic at the size this is drawn.
            f *= 0.94 + 0.06 * min(1.0, hn * 1.4)
            img.set(x, y, shade(base, f) + (255,))

    grown = dilate(img, covered, SIZE, SIZE, passes=4)
    img.save(out_path)
    if dbg:
        dbg.save(regions_path)
    counts["padding"] = grown
    return counts, (differ, shared), (y0, y1)


def dilate(img, covered, w, h, passes):
    """Bleeds the painted islands outward into the empty gutters.

    An auto-packed atlas leaves gaps between islands, and every texel in one
    is transparent black here because nothing on the mesh lands there. The
    sampler does not respect island boundaries: filtering along an edge mixes
    the garment with whatever is beside it, so a uniform with unpadded UVs
    gets a dark fringe down every seam -- on the sleeve heads and the collar,
    which is exactly where a person looks.

    Vanilla's own clothing textures are padded the same way. Four passes is
    enough for the mip levels the game actually samples at this size.
    """
    filled = 0
    mask = bytearray(covered)
    for _ in range(passes):
        additions = []
        for y in range(h):
            for x in range(w):
                k = y * w + x
                if mask[k]:
                    continue
                r = g = b = n = 0
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        nx, ny = x + dx, y + dy
                        if not (0 <= nx < w and 0 <= ny < h):
                            continue
                        if not mask[ny * w + nx]:
                            continue
                        c = img.get(nx, ny)
                        r, g, b, n = r + c[0], g + c[1], b + c[2], n + 1
                if n:
                    additions.append((x, y, (r // n, g // n, b // n, 255)))
        for x, y, c in additions:
            img.set(x, y, c)
            mask[y * w + x] = 1
        filled += len(additions)
        if not additions:
            break
    return filled


# How near the centre line a texel has to be to count as the collar rather
# than the shoulder. Height alone does not separate them: the top of the
# shoulder *is* the highest part of the torso, so a collar defined by height
# came out as a black band from sleeve head to sleeve head. Measured from the
# rigs -- the neck opening sits inside 0.07.
NECK_X = 0.072


def _collar(reg, hn, p, colour):
    """The collar band and the grey undershirt at the throat, or None."""
    if abs(p[0]) > NECK_X:
        return None
    if hn > 0.985:
        return UNDERSHIRT
    if hn > 0.952:
        return COLLAR
    return None


def _duty_colour(reg, hn, p, colour, g):
    """The duty one-piece: division above the waist, black below it."""
    if reg == "lower":
        return BLACK
    if reg == "sleeve":
        return colour
    if reg == "yoke":
        return _collar(reg, hn, p, colour) or colour
    # torso: division colour, with the waist seam just above the trousers
    if hn < g.lower_top + 0.012:
        return PIPING
    return colour


def _dress_colour(reg, hn, p, colour, g):
    """The dress robe: black, with a division bodice, yoke and sleeves."""
    if reg == "lower":
        return BLACK
    if reg == "sleeve":
        return colour
    if reg == "yoke":
        return _collar(reg, hn, p, colour) or colour
    # the bodice: a division panel down to the waist, then the black skirt
    if hn > g.torso_top - 0.09:
        return colour
    if hn > g.torso_top - 0.102:
        return PIPING
    return BLACK


# ---------------------------------------------------------------------------
# Icons, rendered from the rig itself
# ---------------------------------------------------------------------------
def icon_from_mesh(mesh, texture, out_path, scratch):
    """An icon that is the same object as the worn garment.

    Rendered rather than drawn, for the reason `gen_batleth.py` renders its
    own: the icon and the thing in the world cannot then drift apart. The
    preview's flat backdrop is keyed by **exact match** -- a colour ramp would
    eat the black of the trousers, which is 12 away from it.
    """
    big = os.path.join(scratch, "icon_big.png")
    render(mesh, texture, big, size=ICON * 6, yaw_deg=0)
    w, h, px = read_png_rgba(big)

    # Trim to what was actually drawn, so the garment fills its frame instead
    # of floating in the renderer's margin.
    minx, miny, maxx, maxy = w, h, -1, -1
    for y in range(h):
        for x in range(w):
            i = (y * w + x) * 4
            if (px[i], px[i + 1], px[i + 2]) != PREVIEW_BG:
                minx, miny = min(minx, x), min(miny, y)
                maxx, maxy = max(maxx, x), max(maxy, y)
    if maxx < 0:
        raise SystemExit(f"{out_path}: the render is empty")

    bw, bh = maxx - minx + 1, maxy - miny + 1
    side = max(bw, bh)
    ox, oy = minx - (side - bw) // 2, miny - (side - bh) // 2

    img = Image(ICON, ICON, (0, 0, 0, 0))
    step = side / float(ICON)
    filled = 0
    for y in range(ICON):
        for x in range(ICON):
            # Box-filter the supersampled render down, skipping backdrop so
            # the edge does not pick up a dark halo.
            r = g = b = n = 0
            for sy in range(int(y * step), int((y + 1) * step)):
                for sx in range(int(x * step), int((x + 1) * step)):
                    px_x, px_y = ox + sx, oy + sy
                    if not (0 <= px_x < w and 0 <= px_y < h):
                        continue
                    i = (px_y * w + px_x) * 4
                    c = (px[i], px[i + 1], px[i + 2])
                    if c == PREVIEW_BG:
                        continue
                    r, g, b, n = r + c[0], g + c[1], b + c[2], n + 1
            if n:
                img.set(x, y, (r // n, g // n, b // n, 255))
                filled += 1
    img.save(out_path)
    return filled / float(ICON * ICON)


# ---------------------------------------------------------------------------
def build(root, scratch):
    tex_dir = os.path.join(root, "media", "textures", "clothes", "trek")
    icon_dir = os.path.join(root, "media", "textures")
    art = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "design", "art", "uniforms")
    for d in (tex_dir, icon_dir, art, scratch):
        os.makedirs(d, exist_ok=True)

    sources = {
        "duty": os.path.join(PZ, "media", "textures", "clothes",
                             "BolierSuit", "Boilersuit_Grey.png"),
        "dress": os.path.join(PZ, "media", "textures", "Clothes",
                              "Dress_Textures", "judgesrobes.png"),
    }

    made = []
    for garment in (DUTY, DRESS):
        for division, colour in DIVISIONS.items():
            stem = f"{garment.key}_{division.lower()}"
            out = os.path.join(tex_dir, stem + ".png")
            dbg = os.path.join(art, f"regions_{garment.key}.png") \
                if division == "Command" else None
            counts, (differ, shared), (y0, y1) = paint(
                garment, colour, out, sources.get(garment.key), dbg)

            empty = [r for r in ("sleeve", "yoke", "torso", "lower")
                     if counts[r] == 0]
            if empty:
                raise SystemExit(
                    f"{stem}: no texel landed in {', '.join(empty)} -- the "
                    f"height thresholds no longer match the rig, and this "
                    f"texture would ship a uniform missing that panel")
            if counts["badge"] == 0:
                raise SystemExit(
                    f"{stem}: the combadge covered nothing. It is placed in "
                    f"world space on the front-left of the chest; if the rig "
                    f"moved, so did it.")

            print(f"  {stem:<20} sleeve {counts['sleeve']:5d}  "
                  f"yoke {counts['yoke']:5d}  torso {counts['torso']:5d}  "
                  f"lower {counts['lower']:5d}  badge {counts['badge']:4d}")
            made.append((garment, division, out))

        # Both bodies wear one texture, so the panels have to land in the same
        # places on each. A few tenths of a percent along a seam is the two
        # figures being different shapes; a few percent is two layouts.
        pct = 100.0 * differ / shared if shared else 100.0
        print(f"  {garment.name}: {shared} shared texels, {differ} "
              f"({pct:.2f}%) land in a different panel on the two bodies "
              f"(height {y0:.3f}..{y1:.3f})")
        if shared < 10000:
            raise SystemExit(
                f"{garment.name}: only {shared} texels are covered by both "
                f"rigs -- the maps are not being read, so this check proves "
                f"nothing (DEV_GUIDE: a check against an empty set is not a "
                f"passing check)")
        if pct > 2.0:
            raise SystemExit(
                f"{garment.name}: {pct:.1f}% of shared texels are a different "
                f"panel on the male and female rigs. They share one texture, "
                f"so one body would wear a scrambled uniform.")

    # Icons, from the male rig of each garment.
    for garment, division, tex in made:
        icon = os.path.join(icon_dir, f"Item_TREK_{garment.key.title()}"
                                      f"{division}.png")
        fill = icon_from_mesh(os.path.join(RIGS, garment.rigs[0]), tex,
                              icon, scratch)
        print(f"  icon {os.path.basename(icon):<34} {fill * 100:4.0f}% filled")

    write_clothing(root, made)
    sheet(made, art, scratch)
    return made


# ---------------------------------------------------------------------------
# The clothing XML and the GUID table
# ---------------------------------------------------------------------------
# Every clothing item is reached by **GUID**, never by name:
# `OutfitManager.getClothingItem` calls `getFilePathFromGuid` first and
# returns null at bci 12 when the table does not know it. So an item whose
# GUID row is missing equips, weighs, insulates, gets dirty -- and draws
# nothing at all, with no warning anywhere. That is the sixth instance in this
# project of a thing that is present, drawn and inert, so the table is
# generated from the same list that writes the textures rather than
# maintained by hand.
#
# `ZomboidFileSystem.loadFileGuidTable` walks getModIDs() and merges a
# fileGuidTable.xml from the mod's common dir *and* its version dir, so
# TrekShuttle/42/media/fileGuidTable.xml is a supported location. The merge is
# a plain ArrayList.addAll with no de-duplication, which is why the GUIDs here
# are namespaced and checked against all 1,795 of vanilla's in test_assets.py.
GUID_NAMESPACE = "trekshuttle.clothing."


def clothing_guid(stem):
    """A stable GUID for one clothing item.

    uuid5 of a fixed namespace, so regenerating produces the same table and a
    save's clothing keeps resolving. A random uuid4 here would silently orphan
    every uniform already in a world the moment anybody re-ran the generator.
    """
    import uuid
    return str(uuid.uuid5(uuid.NAMESPACE_URL, GUID_NAMESPACE + stem))


# Which rig each garment borrows, and the mask set vanilla uses with it. The
# masks decide which parts of the body the garment hides; they are copied from
# the vanilla item that already wears this exact geometry, because the mesh is
# unchanged and so is the answer.
RIG_XML = {
    "duty": {
        "male": "skinned\\clothes\\bob_boilersuit",
        "female": "skinned\\clothes\\kate_boilersuit",
        "masks": [14, 15, 3, 5, 7, 9],
        "masks_folder": None,
    },
    "dress": {
        "male": "skinned\\clothes\\bob_judegsrobe",
        "female": "skinned\\clothes\\kate_judegsrobe",
        "masks": [12, 13, 14, 15, 3, 5, 7, 9, 11],
        "masks_folder": "media/textures/Clothes/Dress_Textures/JudgeRobeMask",
    },
}


def clothing_name(garment, division):
    return f"TrekUniform{garment.key.title()}{division}"


def write_clothing(root, made):
    """Writes one clothing XML per uniform, and the mod's own GUID table."""
    out_dir = os.path.join(root, "media", "clothing", "clothingItems")
    os.makedirs(out_dir, exist_ok=True)
    rows = []
    for garment, division, _tex in made:
        stem = clothing_name(garment, division)
        rig = RIG_XML[garment.key]
        guid = clothing_guid(stem)
        texture = f"clothes\\trek\\{garment.key}_{division.lower()}"

        lines = ['<?xml version="1.0" encoding="utf-8"?>',
                 "<clothingItem>",
                 f"\t<m_GUID>{guid}</m_GUID>",
                 f"\t<m_MaleModel>{rig['male']}</m_MaleModel>",
                 f"\t<m_FemaleModel>{rig['female']}</m_FemaleModel>",
                 "\t<m_AltMaleModel></m_AltMaleModel>",
                 "\t<m_AltFemaleModel></m_AltFemaleModel>",
                 "\t<m_Static>false</m_Static>",
                 "\t<m_AllowRandomHue>false</m_AllowRandomHue>",
                 # Starfleet issue is Starfleet issue: a random tint would put
                 # a lilac command uniform on somebody.
                 "\t<m_AllowRandomTint>false</m_AllowRandomTint>",
                 "\t<m_AttachBone></m_AttachBone>"]
        for m in rig["masks"]:
            lines.append(f"\t<m_Masks>{m}</m_Masks>")
        if rig["masks_folder"]:
            lines.append(f"\t<m_MasksFolder>{rig['masks_folder']}</m_MasksFolder>")
            lines.append(f"\t<m_UnderlayMasksFolder>{rig['masks_folder']}"
                         f"</m_UnderlayMasksFolder>")
        lines.append(f"\t<textureChoices>{texture}</textureChoices>")
        lines.append("</clothingItem>")

        path = os.path.join(out_dir, stem + ".xml")
        with open(path, "w", encoding="utf-8", newline="\r\n") as fh:
            fh.write("\n".join(lines) + "\n")
        rows.append((f"media/clothing/clothingItems/{stem}.xml", guid))

    table = ['<?xml version="1.0" encoding="utf-8"?>', "<fileGuidTable>"]
    for path, guid in rows:
        table += ["\t<files>", f"\t\t<path>{path}</path>",
                  f"\t\t<guid>{guid}</guid>", "\t</files>"]
    table.append("</fileGuidTable>")
    guid_path = os.path.join(root, "media", "fileGuidTable.xml")
    with open(guid_path, "w", encoding="utf-8", newline="\r\n") as fh:
        fh.write("\n".join(table) + "\n")
    print(f"  {len(rows)} clothing XMLs and media/fileGuidTable.xml")
    return rows


def sheet(made, art, scratch):
    """Both garments, every division, on both bodies -- the vet.

    The generator and the vet are one command, which is the pattern
    `gen_torpedo_flight.py` set: a sheet written by hand goes stale the first
    time a constant changes, and then it is evidence for a build that no
    longer exists.

    **Both bodies are on it on purpose.** They share one texture, so the male
    render alone cannot show a female one going wrong -- and a character
    nobody happened to make is exactly where this would have hidden.
    """
    cells, size = [], 300
    for garment, division, tex in made:
        for which, rig in (("M", garment.rigs[0]), ("F", garment.rigs[1])):
            out = os.path.join(scratch, f"sheet_{garment.key}_{division}_{which}.png")
            render(os.path.join(RIGS, rig), tex, out, size=size, yaw_deg=0)
            cells.append((f"{garment.key} {division.lower()} {which}", out))

    cols = 4
    rows = (len(cells) + cols - 1) // cols
    pad, lab = 8, 12
    out = Image(pad + cols * (size + pad), pad + rows * (size + lab + pad),
                (28, 30, 36, 255))
    for i, (caption, path) in enumerate(cells):
        r, c = divmod(i, cols)
        ox = pad + c * (size + pad)
        oy = pad + r * (size + lab + pad)
        w, h, px = read_png_rgba(path)
        for y in range(min(h, size)):
            for x in range(min(w, size)):
                k = (y * w + x) * 4
                out.set(ox + x, oy + y, (px[k], px[k + 1], px[k + 2], 255))
        from pngwrite import draw_text
        draw_text(out, caption.upper(), ox + 2, oy + size + 2, (226, 230, 240, 255))
    dest = os.path.join(art, "uniform_sheet.png")
    out.save(dest)
    print(f"  sheet {dest}")
    return dest


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else "TrekShuttle/42"
    scratch = os.environ.get("TREK_SCRATCH") or os.path.join(root, "_scratch")
    os.makedirs(scratch, exist_ok=True)
    print("uniforms:")
    build(root, scratch)
