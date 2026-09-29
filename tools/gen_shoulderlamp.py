"""The shoulder lamp: mesh, texture, icon, where it sits, and the renders.

    python tools/gen_shoulderlamp.py TrekShuttle/42

Writes
    media/models_X/TREK_ShoulderLamp.x          a small lamp, lens forward
    media/textures/TREK_ShoulderLamp.png        the case, the lens, the delta
    media/textures/Item_TREK_ShoulderLamp.png   32x32, rendered from the mesh
    media/scripts/trekshuttle.txt               TrekShoulderLampModel's attachments
    design/art/shoulderlamp/lamp_sheet.png      the model, and the icon at 64/32
    design/art/shoulderlamp/lamp_worn.png       worn on both bodies, and in hand

**Where it sits is solved, not typed.** The Shoulder slot hangs the lamp on
vanilla's `webbing_right_walkie`, high on the right of the chest on Spine1,
because it is the same point on both bodies and no vanilla model has to be
edited to use it. The engine draws an attached model at bone x the body's
attachment x the model's own attachment of the same name (DEV_GUIDE, *A weapon
model is a static mesh*), so the lamp's own `webbing_right_walkie` is what
lifts it from the chest to the top of the shoulder and turns its lens to face
where the wearer faces. Both are worked out here from the skeleton -- the
right upper arm's joint, a little in and up and forward of it -- and written
into the script, then drawn on both bodies by that same rule so the sheet is
the check. A number typed into the script would be right only until the mesh
changed.

The icon is **32x32** because the item has an AttachmentType: vanilla's
hotbar centres an icon by half its own width (DEV_GUIDE, same section).

Units are the character's: 0.98 units is about 1.8 m. The lamp is drawn a
little larger than life -- 7 x 5 cm of lens -- because at the size the game
draws a character a real one is two pixels.
"""

import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np

from meshbuild import MeshBuilder
from pngwrite import Image, draw_text
from preview_model import read_png_rgba, render

# Case, in model units: x across, y up, z forward (the lens faces +z).
HW, HH, D = 0.020, 0.015, 0.024       # half width, half height, depth
LENS_IN = 0.004                         # the lens sits this far inside the bezel
TEX = 64

LENS = (0, 0, 32, 24)
FRONT = (32, 0, 64, 24)     # the bezel round the lens, drawn as a frame
SIDE = (0, 28, 32, 44)
TOP = (32, 28, 64, 44)
BACK = (0, 48, 32, 64)

CASE = (150, 154, 164)
CASE_DARK = (74, 78, 88)
BEZEL = (52, 54, 62)
GOLD = (230, 190, 90)
LENS_EDGE = (150, 190, 230)
LENS_MID = (225, 240, 255)
LENS_HOT = (255, 255, 255)
PREVIEW_BG = (28, 30, 36)

ATTACH = "webbing_right_walkie"
# Where the lamp's back goes, from the right upper arm's joint, in the body's
# own frame: x toward the wearer's right, y up, z forward. Over the joint and
# a little below it, forward onto the front of the deltoid, where a lamp on a
# shoulder strap rides and the light is not in the wearer's face. Judged on
# torso close-ups of both bodies: the first guess -- in and up from the
# joint, "on top of the shoulder" -- sat against the collar.
FROM_ARM = (0.004, -0.012, 0.036)
# Tipped down a little, as a lamp on a shoulder strap is, so the cone lands on
# the ground a few paces ahead rather than at the horizon.
TILT_DOWN = 8.0


def paint():
    img = Image(TEX, TEX, CASE + (255,))
    x0, y0, x1, y1 = LENS
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    for y in range(y0, y1):
        for x in range(x0, x1):
            d = math.hypot((x + 0.5 - cx) / (x1 - x0), (y + 0.5 - cy) / (y1 - y0))
            c = LENS_HOT if d < 0.14 else LENS_MID if d < 0.32 else LENS_EDGE
            img.set(x, y, c + (255,))
    fx0, fy0, fx1, fy1 = FRONT
    img.rect(fx0, fy0, fx1, fy1, BEZEL + (255,))
    for region in (SIDE, TOP):
        rx0, ry0, rx1, ry1 = region
        img.rect(rx0, ry0, rx1, ry1, CASE + (255,))
        img.rect(rx0, ry0, rx1, ry0 + 2, CASE_DARK + (255,))
    # A gold stripe along the top: the ship's trim, and the one thing that
    # still reads at 32px as Starfleet rather than hardware-store.
    tx0, ty0, tx1, ty1 = TOP
    img.rect(tx0, (ty0 + ty1) // 2 - 2, tx1, (ty0 + ty1) // 2 + 2, GOLD + (255,))
    bx0, by0, bx1, by1 = BACK
    img.rect(bx0, by0, bx1, by1, CASE_DARK + (255,))
    img.rect(bx0 + 10, by0 + 2, bx1 - 10, by1 - 2, BEZEL + (255,))
    return img


def mesh():
    """A case with a bezel on the front and the lens set into it, a clip on
    the back. The origin is the middle of the back face, where it meets the
    uniform, so the attachment's offset is where the back goes."""
    mb = MeshBuilder(TEX, TEX, up_axis="y")
    P = mb.place           # (across, forward, up)

    def face(p0, p1, p2, p3, region, normal):
        # Winding is what the game culls on, and it is decided in the
        # (east, north, height) frame before place() swaps to Y-up -- the
        # PADD's and the box's convention: (p1 - p0) x (p2 - p0) points out.
        # A quad written the other way round is mirrored across, not dropped.
        a, b_, c = (np.array(p) for p in (p0, p1, p2))
        if np.dot(np.cross(b_ - a, c - a), normal) < 0:
            p0, p1, p2, p3 = p1, p0, p3, p2
        mb.quad(P(*p0), P(*p1), P(*p2), P(*p3), region, P(*normal))

    b = 0.0035             # bezel width
    f = D                  # the front plane
    # Four sides of the case, back plane 0 to front plane D.
    face((-HW, 0, -HH), (HW, 0, -HH), (HW, f, -HH), (-HW, f, -HH), SIDE, (0, 0, -1))   # bottom
    face((-HW, f, HH), (HW, f, HH), (HW, 0, HH), (-HW, 0, HH), TOP, (0, 0, 1))         # top
    face((HW, 0, -HH), (HW, 0, HH), (HW, f, HH), (HW, f, -HH), SIDE, (1, 0, 0))        # right
    face((-HW, f, -HH), (-HW, f, HH), (-HW, 0, HH), (-HW, 0, -HH), SIDE, (-1, 0, 0))   # left
    # Back, against the uniform.
    face((HW, 0, -HH), (-HW, 0, -HH), (-HW, 0, HH), (HW, 0, HH), BACK, (0, -1, 0))
    # The bezel: four strips of the front plane round the opening.
    ix, iz = HW - b, HH - b
    face((-HW, f, -HH), (HW, f, -HH), (HW, f, -iz), (-HW, f, -iz), FRONT, (0, 1, 0))
    face((-HW, f, iz), (HW, f, iz), (HW, f, HH), (-HW, f, HH), FRONT, (0, 1, 0))
    face((-HW, f, -iz), (-ix, f, -iz), (-ix, f, iz), (-HW, f, iz), FRONT, (0, 1, 0))
    face((ix, f, -iz), (HW, f, -iz), (HW, f, iz), (ix, f, iz), FRONT, (0, 1, 0))
    # The recess walls, and the lens at the bottom of it.
    li = f - LENS_IN
    face((-ix, li, -iz), (ix, li, -iz), (ix, f, -iz), (-ix, f, -iz), FRONT, (0, 0, 1))
    face((-ix, f, iz), (ix, f, iz), (ix, li, iz), (-ix, li, iz), FRONT, (0, 0, -1))
    face((ix, li, -iz), (ix, li, iz), (ix, f, iz), (ix, f, -iz), FRONT, (-1, 0, 0))
    face((-ix, f, -iz), (-ix, f, iz), (-ix, li, iz), (-ix, li, -iz), FRONT, (1, 0, 0))
    face((-ix, li, -iz), (ix, li, -iz), (ix, li, iz), (-ix, li, iz), LENS, (0, 1, 0))
    return mb


# --- where it sits --------------------------------------------------------

def rotate_xyz(p, rot):
    """JOML's rotateXYZ, as makeAttachmentTransform applies it: Rx Ry Rz
    (gen_batleth.py, checked against the game)."""
    x, y, z = p
    ax, ay, az = (math.radians(a) for a in rot)
    x, y = x * math.cos(az) - y * math.sin(az), x * math.sin(az) + y * math.cos(az)
    x, z = x * math.cos(ay) + z * math.sin(ay), -x * math.sin(ay) + z * math.cos(ay)
    y, z = y * math.cos(ax) - z * math.sin(ax), y * math.sin(ax) + z * math.cos(ax)
    return (x, y, z)


def matrix_of(rot):
    return np.array([rotate_xyz(e, rot) for e in ((1, 0, 0), (0, 1, 0), (0, 0, 1))]).T


def euler_of(m):
    """The (x, y, z) degrees rotate_xyz turns into `m` (m = Rx Ry Rz)."""
    ay = math.asin(max(-1.0, min(1.0, m[0, 2])))
    ax = math.atan2(-m[1, 2], m[2, 2])
    az = math.atan2(-m[0, 1], m[0, 0])
    rot = tuple(round(math.degrees(a), 4) + 0.0 for a in (ax, ay, az))
    err = np.abs(matrix_of(rot) - m).max()
    if err > 1e-3:
        raise SystemExit(f"euler_of: {rot} reproduces the rotation to {err:.4f} only")
    return rot


def body_attachment(name, body):
    from figure_render import PZ
    src = open(os.path.join(PZ, "scripts", "generated", "models_characters.txt")).read()
    block = re.search(r"model %s\s*\{(.*?)\n    \}" % body, src, re.S).group(1)
    m = re.search(r"attachment %s\s*\{(.*?)\}" % name, block, re.S).group(1)
    num = lambda key: tuple(float(v) for v in re.search(key + r"\s*=\s*([-\d. ]+),", m).group(1).split())
    bone = re.search(r"bone\s*=\s*(\w+)", m).group(1)
    return num("offset"), num("rotate"), bone


def solve(pose, body):
    """The lamp's own (offset, rotate) for ATTACH on this body, in this pose.

    world(v) = W(A(own(v))), with A the body's attachment and W the bone's
    world transform (row vectors, xskin's). Every map in the chain is affine,
    so it is read off by pushing points through it, and the own transform
    that sends the mesh's back to the target and its axes to the wearer's is
    solved in closed form."""
    import xskin
    off, rot, bone = body_attachment(ATTACH, body)
    W = pose.world[bone]

    def chain(v):      # the lamp's own point -> world, with own = identity
        return np.array(xskin.transform(tuple(np.add(rotate_xyz(v, rot), off)), W))

    o = chain((0, 0, 0))
    M = np.array([chain(e) - o for e in ((1, 0, 0), (0, 1, 0), (0, 0, 1))]).T

    def at(b):
        return np.array(xskin.transform((0, 0, 0), pose.world[b]))

    # The body's own frame, read off the skeleton rather than derived (DEV_GUIDE,
    # *Ask the asset which way round it is*): its right is where the Bip01_R_
    # bones are, and forward is where the toes point. Not a cross product of
    # the two -- the frame is Direct3D's, left-handed, and the forearms in the
    # idle hang *behind* the neck, so neither is a safe thing to reason from.
    right = at("Bip01_R_UpperArm") - at("Bip01_L_UpperArm")
    right /= np.linalg.norm(right)
    up = np.array([0.0, 1.0, 0.0])
    toes = at("Bip01_R_Toe0") - at("Bip01_R_Foot")
    fwd = toes - np.dot(toes, up) * up - np.dot(toes, right) * right
    fwd /= np.linalg.norm(fwd)
    target = at("Bip01_R_UpperArm") + FROM_ARM[0] * right + FROM_ARM[1] * up + FROM_ARM[2] * fwd
    t = math.radians(TILT_DOWN)
    lens = fwd * math.cos(t) - up * math.sin(t)
    lamp_up = np.cross(lens, right)
    if lamp_up[1] < 0:
        lamp_up = -lamp_up
    across = np.cross(lamp_up, lens)
    # The mesh's x, y, z are across, up and lens.
    D_ = np.array([across, lamp_up, lens]).T
    own_m = np.linalg.solve(M, D_)
    # M carries the bone's scale, if any; the own rotation must not.
    u, _, vt = np.linalg.svd(own_m)
    own_m = u @ vt
    own_off = np.linalg.solve(M, target - o)
    # rotate_xyz(v) then + offset is what the engine applies: T(off) * R.
    return tuple(round(float(x), 4) + 0.0 for x in own_off), euler_of(own_m)


def write_model_block(script, own):
    """TrekShoulderLampModel, with its shoulder attachment and a hand one."""
    (off, rot) = own
    lines = ["    model TrekShoulderLampModel", "    {",
             "        mesh = TREK_ShoulderLamp,",
             "        texture = TREK_ShoulderLamp,",
             "        scale = 1.0,",
             f"        attachment {ATTACH}", "        {",
             "            offset = %s %s %s," % off,
             "            rotate = %s %s %s," % rot, "        }",
             # In a fist the lens goes where a blade goes, up the prop's +Y
             # (DEV_GUIDE: a blade runs +Y from the grip). A first guess, to
             # be judged in hand as the PADD's and the blades' were.
             "        attachment Bip01_Prop2", "        {",
             "            offset = 0.0 0.0 0.0,",
             "            rotate = -90.0 0.0 0.0,", "        }",
             "    }"]
    raw = open(script, "rb").read().decode("utf-8")
    nl = "\r\n" if "\r\n" in raw else "\n"
    pat = re.compile(r"    model TrekShoulderLampModel\r?\n    \{.*?\r?\n    \}", re.S)
    if len(pat.findall(raw)) != 1:
        raise SystemExit(f"FAILED: TrekShoulderLampModel not found once in {script}")
    new = pat.sub(lambda _: nl.join(lines), raw)
    open(script, "wb").write(new.encode("utf-8"))
    print(f"script  {script} (TrekShoulderLampModel: {ATTACH} {off} {rot})")


def own_attachment(script, name):
    text = open(script, encoding="utf-8").read()
    block = re.search(r"model TrekShoulderLampModel\s*\{(.*?)\n    \}", text, re.S).group(1)
    m = re.search(r"attachment %s\s*\{(.*?)\}" % name, block, re.S).group(1)
    num = lambda key: tuple(float(v) for v in re.search(key + r"\s*=\s*([-\d. ]+),", m).group(1).split())
    return num("offset"), num("rotate")


def render_worn(x_path, tex_path, script, out, poses):
    """The lamp on both bodies, by the engine's rule from the numbers now in
    the script, in the duty uniform it hangs from -- and in hand."""
    from PIL import Image as PILImage
    from figure_render import PZ, Figure, render as frender
    from preview_model import parse_x

    verts, faces, uvs = parse_x(x_path)
    own_off, own_rot = own_attachment(script, ATTACH)
    tex_root = os.path.dirname(os.path.dirname(tex_path))
    rows = []
    for sex, body, pose in poses:
        off, rot, bone = body_attachment(ATTACH, body)
        fig = Figure(pose)
        fig.body(os.path.join(PZ, "textures", "Body", "MaleBody01.png" if sex == "M" else "FemaleBody01.png"))
        rig = "bob_boilersuit" if sex == "M" else "kate_boilersuit"
        fig.garment(os.path.join(PZ, "models_X", "Skinned", "Clothes", rig + ".X"),
                    os.path.join(tex_root, "textures", "clothes", "trek", "duty_command.png"))
        placed = [tuple(np.add(rotate_xyz(tuple(np.add(rotate_xyz(v, own_rot), own_off)), rot), off))
                  for v in verts]
        fig.static(placed, faces, uvs, tex_path, bone)
        rows.append([frender(fig, size=240, yaw=y, pitch=30, ss=2) for y in (0, -45, -90, 180)])
    sex, body, pose = poses[0]
    hoff, hrot = own_attachment(script, "Bip01_Prop2")
    fig = Figure(pose)
    fig.body(os.path.join(PZ, "textures", "Body", "MaleBody01.png"))
    fig.static([tuple(np.add(rotate_xyz(v, hrot), hoff)) for v in verts], faces, uvs, tex_path,
               "Bip01_Prop2")
    rows.append([frender(fig, size=240, yaw=y, pitch=30, ss=2) for y in (0, -45, -90, 180)])
    sheet = PILImage.new("RGB", (240 * 4, 240 * len(rows)))
    for j, row in enumerate(rows):
        for i, tile in enumerate(row):
            sheet.paste(tile, (i * 240, j * 240))
    sheet.save(out)
    print(f"worn    {out} (male, female, in hand)")


def icon_from(render_path, out_path, size):
    """gen_padd's crop and alpha-weighted shrink, at the hotbar's size."""
    from gen_padd import icon_from as padd_icon
    return padd_icon(render_path, out_path, size)


def build(root, art):
    from figure_render import Pose
    media = os.path.join(root, "media")
    os.makedirs(art, exist_ok=True)
    tex_path = os.path.join(media, "textures", "TREK_ShoulderLamp.png")
    paint().save(tex_path)
    x_path = os.path.join(media, "models_X", "TREK_ShoulderLamp.x")
    nv, nf = mesh().emit(x_path, "TREK_ShoulderLamp", "TREK_ShoulderLamp.png")
    print(f"TREK_ShoulderLamp: {nv} vertices, {nf} faces, {2 * HW} x {2 * HH} x {D}")

    renders = []
    for name, yaw in (("iso", 145), ("front", 180)):
        p = os.path.join(art, f"_lamp_{name}.png")
        render(x_path, tex_path, p, size=256, yaw_deg=yaw)
        renders.append(p)
    icon_path = os.path.join(media, "textures", "Item_TREK_ShoulderLamp.png")
    covered = icon_from(renders[0], icon_path, 32)
    print(f"icon    {icon_path}: {covered} of 1024 pixels covered")

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
    sheet.save(os.path.join(art, "lamp_sheet.png"))
    print("sheet  ", os.path.join(art, "lamp_sheet.png"))

    # Solved on the male body in the idle, where it is seen most; drawn on
    # both, because one attachment serves both and Kate's spine is not Bob's.
    poses = [("M", "MaleBody", Pose("M", "Bob_Idle.X")), ("F", "FemaleBody", Pose("F", "Bob_Idle.X"))]
    own = solve(poses[0][2], "MaleBody")
    script = os.path.join(media, "scripts", "trekshuttle.txt")
    write_model_block(script, own)
    render_worn(x_path, tex_path, script, os.path.join(art, "lamp_worn.png"), poses)


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else os.path.join("TrekShuttle", "42")
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    build(root, os.path.join(here, "design", "art", "shoulderlamp"))
