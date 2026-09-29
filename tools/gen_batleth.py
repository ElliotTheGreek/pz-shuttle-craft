"""Builds the bat'leth: mesh, in-hand texture, and nothing else.

    python tools/gen_batleth.py TrekShuttle/42

A bat'leth is a shallow crescent held by a wrapped bar along its *convex back*,
over three hand-holes cut through the blade; the cutting edge is the concave
side and the long swept tips. Its four points are those two tips and a spike
off the cutting edge at each end, and where the grip bar ends it juts into a
short back point. The first version had all of that inside out -- grips on the
concave edge, spikes on the back, no holes -- and read in game as a pair of
horns; the props in the Wikipedia article's photograph are what this follows.

It is drawn as a flat ribbon of bands following a curved centreline -- the
blade below the holes, the struts between them, the grip bar above -- each a
front and back face with rims, because the shape is a 2D silhouette given
thickness and every edge is then one function of the distance along the arc.

**The tips point along +Y, away from the fist.** The origin is the middle of
the grip bar, where the hands go, and a weapon's +Y is the direction the blade
goes from the hand (vanilla's katana runs from -0.05 at the pommel to +0.58).
The first version had its tips on -Y, so it was held back to front with both
points in the wielder's chest.

**On the back it needs its own attachments.** The back slots hang a weapon by
its Y axis, a katana's length, and a bat'leth's length is its X: with no
attachment of its own it stood on edge across the shoulders like horns. The
engine draws an attached item at bone x the character's attachment x *the
item's own attachment of the same name* (`AttachedModelName` sets self =
parent; `transformToParent`, and `invertAttachmentSelfTransformZ` is never set),
so `blade_back` and `big_blade_back_bag` in `trekweapons.txt` turn it flat onto
the back or the pack. `BACK_MOUNTS` below is where those numbers come from.

Two things about weapon models that cost other people time (see DEV_GUIDE and
the comment on TrekPhaser in trekshuttle.txt):

  * **This is a static mesh. There is no rig.** A weapon model is a `model`
    block naming a mesh and a texture, exactly like a world model; the swing
    comes from `SwingAnim`, a name resolved against the game's own animation
    set. No bones, no skinning, no animation files.
  * **Y is up.** Vanilla weapon meshes are authored Y-up -- their `world`
    attachments offset along y to set how high the weapon lies on the ground.
    The hull and the helm are Z-up, so this is the opposite of every other
    mesh in this repo and is the easy thing to get wrong.

The blade is authored in metres, tip to tip along its chord, because the
engine takes the mesh at face value and vanilla's `scale` lines exist only for
meshes authored in centimetres.
"""
import math
import os
import re
import sys

from meshbuild import MeshBuilder
from pngwrite import Image

TEX_W = TEX_H = 128
UP_AXIS = "y"

# Tip-to-tip chord. **This is model scale, not life scale.** The first version
# was 0.92 -- a real bat'leth is about a metre across -- and in hand it was
# twice the size of the character holding it. WeaponLength (a gameplay reach
# number, 0.45 here) is not what sizes the mesh; this is, and the engine takes
# it at face value.
#
# 0.46 was then still too big, and measuring vanilla says why. Every weapon in
# build 42 is a thin vertical line: the widest mesh in the game's whole arsenal
# is the canoe paddle at dx 0.123, and a machete is 0.009 wide by 0.335 long.
# A bat'leth is the one shape this engine has never had to draw -- a crescent
# worn and swung *across* the body, so its full span reads as width in an
# isometric sprite where a bat of the same real length reads as a stroke. At
# 0.46 the arc bulged the bounding box to 0.531, wider than a baseball bat is
# long, and it spanned the character hip to hip.
#
# So the bracket is not "as long as a katana" but "as wide as a machete is
# long": the old arch's 0.32 chord drew a 0.369 bounding box, the widest a
# cross-body blade reads at before it starts wearing the character rather than
# the other way round, and it was seen at that size in play (2026-09-20). The
# crescent that replaced it has its tips falling rather than bulging past the
# chord, so the chord *is* the width now, and it is set to the width that was
# seen. Real-world scale was never the test; the sprite is.
SPAN = 0.37
THICK = 0.016                   # blade thickness, in metres
SEGMENTS = 160                  # samples along the arc, before the breakpoints

# The centreline's heading, from the grip out to each tip: it turns slowly
# through the grip and fast in the tips, which is what makes a bat'leth a
# shallow crescent with swept points rather than an arch. Degrees at the
# middle of the arc (TURN_LIN) and extra by the tip (TURN_TIP).
TURN_LIN = 44.0
TURN_TIP = 30.0

# How it hangs on the back: per character attachment, the model's own
# `rotate` and where the blade's centre goes, in that attachment's frame.
# Both of vanilla's back slots on Bip01_BackPack have their frame's +X
# pointing straight out of the back and +Y down it (the katana's length), so
# (0, 90, 90) lays the crescent flat on the back with its length where a
# katana's would be: over the right shoulder to the left hip, grip bar to the
# outside. With a pack the slot is nearly vertical, so it is turned 25 degrees
# more, stood 0.12 off the back to sit on the pack's face (the hiking bag's
# back is at +0.238 against the slot's +0.103), and brought 0.1 across to the
# middle of it. Judged on figure_render renders of the male body in Bob_Idle,
# with and without M_HikingBag; the same renderer reproduced the first
# version's horns from a screenshot before these were chosen.
BACK_MOUNTS = (
    ("blade_back", (0.0, 90.0, 90.0), (0.02, 0.18, 0.0)),
    ("big_blade_back_bag", (25.0, 90.0, 90.0), (0.12, 0.14, 0.1)),
)

# Texture regions: (x0, y0, x1, y1)
R_BLADE = (0, 0, 128, 40)       # polished steel, bright along the edge
R_RIM = (0, 40, 128, 56)        # the ground edge, lighter still
R_GRIP = (0, 56, 128, 88)       # wrapped leather on the back bar
R_DARK = (0, 88, 128, 128)      # blued steel inside the hand-holes

STEEL = (188, 196, 204, 255)
STEEL_LIT = (232, 238, 244, 255)
STEEL_DARK = (96, 104, 114, 255)
BLUED = (48, 54, 64, 255)
GRIP = (58, 40, 28, 255)
GRIP_LIT = (92, 66, 46, 255)
BRASS = (150, 118, 58, 255)


def build_texture(path):
    """One strip per region: the blade reads as steel, the grips as leather."""
    img = Image(TEX_W, TEX_H, BLUED)

    # Blade: a bright line along the cutting edge, falling off to shadow at the
    # spine. At the size a weapon is drawn in hand this gradient is the only
    # thing that says "sharpened" rather than "flat grey plank".
    x0, y0, x1, y1 = R_BLADE
    img.rect(x0, y0, x1, y1, STEEL)
    img.rect(x0, y0, x1, y0 + 6, STEEL_LIT)
    img.rect(x0, y1 - 8, x1, y1, STEEL_DARK)
    for i in range(x0, x1, 16):          # faint forging bands
        img.rect(i, y0 + 8, i + 1, y1 - 9, STEEL_DARK)

    x0, y0, x1, y1 = R_RIM
    img.rect(x0, y0, x1, y1, STEEL_LIT)

    # Grips: wrapped leather with brass ferrules at both ends of each binding.
    x0, y0, x1, y1 = R_GRIP
    img.rect(x0, y0, x1, y1, GRIP)
    for i in range(x0, x1, 8):
        img.rect(i, y0, i + 4, y1, GRIP_LIT)
    img.rect(x0, y0, x1, y0 + 3, BRASS)
    img.rect(x0, y1 - 3, x1, y1, BRASS)

    x0, y0, x1, y1 = R_DARK
    img.rect(x0, y0, x1, y1, BLUED)
    img.save(path)


def centreline(t):
    """Point, tangent and convex-side normal of the arc at t in -1..1.

    Measured in half-arc-lengths from the middle of the grip, in the authoring
    frame: the crescent bows upwards and its tips fall to either side. Heading
    is integrated numerically because it is a cubic in t, not a circle."""
    a = abs(t)
    steps = max(1, int(a * 400))
    x = y = 0.0
    for i in range(steps):
        u = (i + 0.5) / steps * a
        phi = math.radians(TURN_LIN * u + TURN_TIP * u ** 3)
        x += math.cos(phi) * a / steps
        y -= math.sin(phi) * a / steps
    phi = math.radians(TURN_LIN * a + TURN_TIP * a ** 3)
    s = 1.0 if t >= 0 else -1.0
    tangent = (math.cos(phi), -s * math.sin(phi))
    return (s * x, y), tangent, (-tangent[1], tangent[0])


# The silhouette, as distances from the centreline along its convex-side
# normal, in half-arc-lengths; a = |t|. Read against the props: a wrapped bar
# over three holes (the middle one under the hands), struts between them, a
# short back point where the bar ends, a spike off the cutting edge below the
# outer strut, and long tips that are the cutting edge carried on and thinned.
GRIP_END = 0.56                     # the bar and the holes stop here
HOLES = ((0.0, 0.13), (0.19, 0.50))  # |t| ranges cut through the blade
TOP, BAR = 0.16, 0.065              # the bar's back edge, and its depth
HOLE_LO = -0.11                     # the holes' lower edge
LOW = -0.18                         # the cutting edge through the middle
POINT = (0.56, 0.645, 0.665, 0.27)  # back point: rises, peaks, falls; height
SPIKE = (0.43, 0.53, 0.555, -0.44)  # the spike: the same, below
TIP_FROM = 0.665                    # where the blade starts thinning to the tip


def in_hole(a):
    return any(lo < a < hi for lo, hi in HOLES)


def top(a):
    r0, pk, r1, h = POINT
    if a <= r0:
        return TOP
    if a <= pk:                      # a long rise and a short fall: it leans out
        return TOP + (h - TOP) * (a - r0) / (pk - r0)
    if a <= r1:
        return h + (0.05 - h) * (a - pk) / (r1 - pk)
    return 0.05 * max(0.0, (1.0 - a) / (1.0 - r1)) ** 0.8


def low(a):
    r0, pk, r1, h = SPIKE
    base = LOW if a <= TIP_FROM else LOW * max(0.0, (1.0 - a) / (1.0 - TIP_FROM)) ** 1.2
    if r0 < a <= pk:
        return LOW + (h - LOW) * (a - r0) / (pk - r0)
    if pk < a < r1:
        return h + (LOW - 0.01 - h) * (a - pk) / (r1 - pk)
    return base


def breakpoints():
    """Every |t| the silhouette turns a corner at, so it is sampled there."""
    ks = {0.0, 1.0, GRIP_END, TIP_FROM, *POINT[:3], *SPIKE[:3]}
    for lo, hi in HOLES:
        ks.update((lo, hi))
    ts = {(-1.0 + 2.0 * i / SEGMENTS) for i in range(SEGMENTS + 1)}
    for k in ks:
        ts.update((k, -k))
    return sorted(ts)


def build_mesh(path, texture_file):
    """The blade in the authoring frame (convex up), then turned half a turn
    about X -- tips to +Y, the flat faces swapped -- which is a rotation, so no
    face winds the wrong way, and scaled so tip to tip is SPAN."""
    m = MeshBuilder(TEX_W, TEX_H, up_axis=UP_AXIS)
    ts = breakpoints()
    tip = centreline(1.0)[0]
    k = SPAN / (2.0 * tip[0])
    half = THICK / 2.0
    grip_mid = (TOP + TOP - BAR) / 2.0          # the hands' line: the origin

    def P(t, n, z):
        (cx, cy), _, (nx, ny) = centreline(t)
        x, y = cx + nx * n, cy + ny * n - grip_mid
        return (x * k, -y * k, -z)

    def N(t, n_sign=0.0, along=0.0, z=0.0):
        _, (tx, ty), (nx, ny) = centreline(t)
        v = (nx * n_sign + tx * along, ny * n_sign + ty * along)
        return (v[0], -v[1], -z)

    def face(pts, uvs, normal):
        """Four points and their texel uvs; wound the way the rest of this
        mod's meshes are (cross of the first two edges against the normal)."""
        a, b, c = pts[0], pts[1], pts[2]
        e1 = [b[i] - a[i] for i in range(3)]
        e2 = [c[i] - a[i] for i in range(3)]
        cr = (e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2],
              e1[0] * e2[1] - e1[1] * e2[0])
        if sum(cr[i] * normal[i] for i in range(3)) > 0:
            pts, uvs = pts[::-1], uvs[::-1]
        whole = (0, 0, TEX_W, TEX_H)
        fr = [(u / TEX_W, v / TEX_H) for u, v in uvs]
        m.tri(pts[0], pts[1], pts[2], whole, normal, (fr[0], fr[1], fr[2]))
        m.tri(pts[0], pts[2], pts[3], whole, normal, (fr[0], fr[2], fr[3]))

    def u_of(t):
        return 2.0 + 124.0 * (t + 1.0) / 2.0

    def band(t0, t1, lo0, hi0, lo1, hi1, region, lit_low):
        """Front and back faces of one band between two samples."""
        x0, y0, x1, y1 = region
        vlo, vhi = (y0 + 1, y1 - 1) if lit_low else (y1 - 1, y0 + 1)
        u0, u1 = u_of(t0), u_of(t1)
        for z, nz in ((half, 1.0), (-half, -1.0)):
            face([P(t0, lo0, z), P(t1, lo1, z), P(t1, hi1, z), P(t0, hi0, z)],
                 [(u0, vlo), (u1, vlo), (u1, vhi), (u0, vhi)], N(0.0, z=nz))

    def rim(t0, t1, n0, n1, outward, region):
        """The edge along the arc at offset n, facing +n (outward=1) or -n."""
        x0, y0, x1, y1 = region
        u0, u1, vm = u_of(t0), u_of(t1), (y0 + y1) / 2.0
        tm = (t0 + t1) / 2.0
        face([P(t0, n0, -half), P(t1, n1, -half), P(t1, n1, half), P(t0, n0, half)],
             [(u0, vm - 3), (u1, vm - 3), (u1, vm + 3), (u0, vm + 3)],
             N(tm, n_sign=outward))

    def cap(t, lo, hi, along):
        """The end wall of a hole, across the arc at t, facing along +-t."""
        x0, y0, x1, y1 = R_DARK
        u, vm = u_of(t), (y0 + y1) / 2.0
        face([P(t, lo, -half), P(t, hi, -half), P(t, hi, half), P(t, lo, half)],
             [(u, vm - 4), (u, vm + 4), (u + 2, vm + 4), (u + 2, vm - 4)],
             N(t, along=along))

    hole_hi = TOP - BAR
    for t0, t1 in zip(ts, ts[1:]):
        a0, a1, am = abs(t0), abs(t1), abs((t0 + t1) / 2.0)
        lo0, lo1, hi0, hi1 = low(a0), low(a1), top(a0), top(a1)
        if am < GRIP_END:
            hole = in_hole(am)
            band(t0, t1, lo0, HOLE_LO, lo1, HOLE_LO, R_BLADE, True)
            band(t0, t1, hole_hi, hi0, hole_hi, hi1, R_GRIP, True)
            if hole:
                rim(t0, t1, HOLE_LO, HOLE_LO, 1.0, R_DARK)
                rim(t0, t1, hole_hi, hole_hi, -1.0, R_DARK)
            else:                    # a strut: steel between the bar and blade
                band(t0, t1, HOLE_LO, hole_hi, HOLE_LO, hole_hi, R_BLADE, False)
            rim(t0, t1, hi0, hi1, 1.0, R_GRIP)
        else:
            band(t0, t1, lo0, hi0, lo1, hi1, R_BLADE, True)
            rim(t0, t1, hi0, hi1, 1.0, R_RIM)
        rim(t0, t1, lo0, lo1, -1.0, R_RIM)

    # The end walls of the holes, wherever a hole meets a strut.
    for t in ts:
        a = abs(t)
        if a >= GRIP_END:
            continue
        for lo, hi in HOLES:
            for edge, into in ((lo, 1.0), (hi, -1.0)):
                if lo == 0.0 and edge == 0.0:
                    continue        # the middle hole runs straight through 0
                if abs(a - edge) < 1e-9:
                    s = 1.0 if t >= 0 else -1.0
                    cap(t, HOLE_LO, hole_hi, into * s)

    nv, nf = m.emit(path, "TREKBatleth", texture_file)
    xs = [v[0] for v in m.verts]
    ys = [v[1] for v in m.verts]
    bbox = (max(xs) - min(xs), max(ys) - min(ys), THICK)
    return nv, nf, (min(ys), max(ys)), bbox


def build_icon(mesh_path, tex_path, out, render_size=512, icon=32, margin=0.10,
               tilt=32.0):
    """The inventory icon, rendered from the mesh this tool just built.

    Two goes at drawing a bat'leth with the image model missed the silhouette:
    the first came back a curved sword with a hilt, the second -- after being
    told at length that it is one thick symmetrical crescent -- a plain arch
    with no forked tips. It is a genuinely awkward shape to describe and an
    easy one to render, and the phaser's icon is already procedural
    (gen_phaser.py), so this follows it.

    The win is not just that it is easier. The icon is now the *same object*
    as the in-hand model, from the same mesh and the same texture, so the two
    cannot drift apart.

    preview_model draws on a flat (28, 30, 36) with no antialiasing, so the
    background is keyed by exact match rather than by a colour ramp. A ramp
    would be wrong here: the grip leather is only 33 away from that
    background, well inside the distance key_icon treats as "probably
    backdrop", and the three hand bindings would have been keyed away.

    **The icon is 32x32, and that is not a style choice.** Every other icon in
    this mod is 64x64 and correct; this one is the only item with an
    `AttachmentType`, so it is the only one vanilla's hotbar ever draws, and
    `ISHotbar.lua:52` draws it like this:

        self:drawTexture(tex, slotX + (tex:getWidth() / 2),
                              (self.height - tex:getHeight()) / 2, 1,1,1,1)

    The y is a real centring expression. The x is not: it is the slot's left
    edge plus *half the texture's own width*, which only lands centred when the
    texture is half the slot. `slotWidth` is 60, so a 32px icon occupies 16..48
    -- centred, as every vanilla icon is -- and a 64px icon occupies 32..96,
    starting at the middle of its own slot and running 36px into the next one.
    Three lines above, vanilla centres the slot label with the formula this
    line should have used, `slotX + (self.slotWidth - textWid) / 2`.

    So the bleed was never the blade being too fat in its frame. It was the
    frame being twice the size vanilla's hotbar assumes, and the three previous
    attempts to fix it by shrinking the drawing -- 94%, then 81%, then 78% --
    were all treating a symptom. At 32x32 the margin goes back to filling the
    frame the way the rest of the set does, because the frame is now the right
    size. Judged on the icon alone every one of those three passes looked
    reasonable; what settled it was reading the code that draws it.
    """
    from PIL import Image as PILImage
    from preview_model import render

    tmp = out + ".render.png"
    render(mesh_path, tex_path, tmp, size=render_size, up_axis=UP_AXIS,
           yaw_deg=0.0)
    src = PILImage.open(tmp).convert("RGBA")
    px = src.load()
    w, h = src.size
    bg = px[0, 0][:3]
    for y in range(h):
        for x in range(w):
            r, g, b, _ = px[x, y]
            if (r, g, b) == bg:
                px[x, y] = (r, g, b, 0)

    # Tilted, because a bat'leth is a shallow crescent: 2.3 times as wide as
    # it is tall, which in a square icon is mostly empty. Vanilla's own blades
    # are all drawn on the diagonal for the same reason. This is a rotation of
    # the finished render, not of the model -- the mesh is what goes in the
    # hand and it must stay level.
    #
    # Turned over first: the mesh has its tips on +Y, away from the hand, which
    # renders them pointing up; a bat'leth is shown the way it hangs on a
    # wall, back up and tips down.
    src = src.rotate(180)
    if tilt:
        src = src.rotate(tilt, resample=PILImage.BICUBIC, expand=True)

    bbox = src.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox()
    if not bbox:
        raise SystemExit("  FAILED: the render is entirely background")
    src = src.crop(bbox)
    side = int(max(src.size) * (1 + margin * 2))
    sq = PILImage.new("RGBA", (side, side), (0, 0, 0, 0))
    sq.paste(src, ((side - src.size[0]) // 2, (side - src.size[1]) // 2))
    sq.resize((icon, icon), PILImage.LANCZOS).save(out, optimize=True)
    os.remove(tmp)
    print(f"  icon    {out} (from the mesh, {bbox[2]-bbox[0]}x{bbox[3]-bbox[1]} "
          f"px of drawn content)")


def rotate_xyz(p, rot):
    """JOML's rotateXYZ, as makeAttachmentTransform applies it: Rx Ry Rz."""
    x, y, z = p
    ax, ay, az = (math.radians(a) for a in rot)
    x, y = x * math.cos(az) - y * math.sin(az), x * math.sin(az) + y * math.cos(az)
    x, z = x * math.cos(ay) + z * math.sin(ay), -x * math.sin(ay) + z * math.cos(ay)
    y, z = y * math.cos(ax) - z * math.sin(ax), y * math.sin(ax) + z * math.cos(ax)
    return (x, y, z)


def write_model_block(script, y_lo, y_hi):
    """Writes TrekBatlethModel into trekweapons.txt with its back attachments.

    An item's own attachment is applied as T(offset) * rotateXYZ(rotate) to
    the mesh, so the offset that puts the blade's centre at `where` is
    `where - R(centre)`. Worked out here from the mesh just built, because a
    number typed into the script would be right only until the next change of
    shape moved the centre."""
    centre = (0.0, (y_lo + y_hi) / 2.0, 0.0)
    lines = ["    model TrekBatlethModel", "    {",
             "        mesh = weapons/2handed/TREK_Batleth,",
             "        texture = weapons/2handed/TREK_Batleth,"]
    for name, rot, where in BACK_MOUNTS:
        c = rotate_xyz(centre, rot)
        off = tuple(round(w - ci, 4) + 0.0 for w, ci in zip(where, c))
        lines += [f"        attachment {name}", "        {",
                  "            offset = %s %s %s," % off,
                  "            rotate = %s %s %s," % rot, "        }"]
    lines.append("    }")
    raw = open(script, "rb").read().decode("utf-8")
    nl = "\r\n" if "\r\n" in raw else "\n"
    pat = re.compile(r"    model TrekBatlethModel\r?\n    \{.*?\r?\n    \}", re.S)
    if len(pat.findall(raw)) != 1:
        raise SystemExit(f"  FAILED: TrekBatlethModel not found once in {script}")
    new = pat.sub(lambda _: nl.join(lines), raw)
    open(script, "wb").write(new.encode("utf-8"))
    print(f"  script  {script} (TrekBatlethModel, "
          f"{', '.join(n for n, _, _ in BACK_MOUNTS)})")


def character_attachments(names, body="MaleBody"):
    """(offset, rotate) of each named attachment on vanilla's body model."""
    from figure_render import PZ
    src = open(os.path.join(PZ, "scripts", "generated", "models_characters.txt")).read()
    block = re.search(r"model %s\s*\{(.*?)\n    \}" % body, src, re.S).group(1)
    out = {}
    for name in names:
        m = re.search(r"attachment %s\s*\{(.*?)\}" % name, block, re.S).group(1)
        num = lambda key: tuple(float(v) for v in
                                re.search(key + r"\s*=\s*([-\d. ]+),", m).group(1).split())
        out[name] = (num("offset"), num("rotate"))
    return out


def render_worn(mesh, tex, script, out):
    """The sheet the back mounts were judged on: the blade on each back slot
    and in the two-handed idle, drawn by the engine's rule from the numbers
    now in the script -- bone x the body's attachment x the blade's own, each
    T(offset) * rotateXYZ(rotate) -- on the male body, with the pack for the
    pack's slot. Written every run, so it cannot go stale."""
    from PIL import Image as PILImage
    from figure_render import PZ, Pose, Figure, render
    from preview_model import parse_x

    def att(p, o_r):
        o, r = o_r
        return tuple(a + b for a, b in zip(rotate_xyz(p, r), o))

    text = open(script).read()
    block = re.search(r"model TrekBatlethModel\s*\{(.*?)\n    \}", text, re.S).group(1)
    own = {}
    for name, _, _ in BACK_MOUNTS:
        m = re.search(r"attachment %s\s*\{(.*?)\}" % name, block, re.S).group(1)
        num = lambda key: tuple(float(v) for v in
                                re.search(key + r"\s*=\s*([-\d. ]+),", m).group(1).split())
        own[name] = (num("offset"), num("rotate"))
    body = character_attachments(own)
    verts, faces, uvs = parse_x(mesh)
    skin = os.path.join(PZ, "textures", "Body", "MaleBody01.png")
    pack = (os.path.join(PZ, "models_X", "Skinned", "Backpacks", "M_HikingBag.X"),
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(tex))),
                         "clothes", "trek", "backpack.png"))
    rows = []
    for name in own:
        fig = Figure(Pose("M", "Bob_Idle.X"))
        fig.body(skin)
        if "bag" in name:
            fig.garment(*pack)
        placed = [att(att(v, own[name]), body[name]) for v in verts]
        fig.static(placed, faces, uvs, tex, "Bip01_BackPack")
        rows.append([render(fig, size=240, yaw=y, pitch=30, ss=2) for y in (180, 135, 90, 45)])
    fig = Figure(Pose("M", "Bob_IdleBat.X"))
    fig.body(skin)
    fig.static(verts, faces, uvs, tex, "Bip01_Prop2")
    rows.append([render(fig, size=240, yaw=y, pitch=30, ss=2) for y in (0, 45, 90, -45)])
    sheet = PILImage.new("RGB", (240 * 4, 240 * len(rows)))
    for j, row in enumerate(rows):
        for i, tile in enumerate(row):
            sheet.paste(tile, (i * 240, j * 240))
    sheet.save(out)
    print(f"  worn    {out} (rows: {', '.join(own)}, in hand)")


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else "TrekShuttle/42"
    mesh_dir = os.path.join(root, "media", "models_X", "weapons", "2handed")
    tex_dir = os.path.join(root, "media", "textures", "weapons", "2handed")
    os.makedirs(mesh_dir, exist_ok=True)
    os.makedirs(tex_dir, exist_ok=True)

    tex = os.path.join(tex_dir, "TREK_Batleth.png")
    mesh = os.path.join(mesh_dir, "TREK_Batleth.x")
    build_texture(tex)
    nv, nf, (y_lo, y_hi), bbox = build_mesh(mesh, "TREK_Batleth.png")
    print(f"bat'leth: {nv} verts, {nf} faces, span {SPAN} m, "
          f"y {y_lo:.3f} (back point) to {y_hi:.3f} (tips) from the grip")
    print(f"  bbox    {bbox[0]:.3f} across x {bbox[1]:.3f} deep x "
          f"{bbox[2]:.3f} thick  (vanilla's widest weapon mesh is the canoe "
          f"paddle at 0.123 across; a machete is 0.335 long)")
    print(f"  mesh    {mesh}")
    print(f"  texture {tex}")
    write_model_block(os.path.join(root, "media", "scripts", "trekweapons.txt"),
                      y_lo, y_hi)
    build_icon(mesh, tex,
               os.path.join(root, "media", "textures", "Item_TREK_Batleth.png"))
    render_worn(mesh, tex, os.path.join(root, "media", "scripts", "trekweapons.txt"),
                os.path.join("design", "art", "weapons", "batleth_worn.png"))
