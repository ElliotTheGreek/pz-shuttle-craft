"""Generates the downed ensign: a vanilla body in the mod's uniform, posed.

    python tools/gen_ensign.py TrekShuttle/42

Writes, for each body (M, F):

    media/models_X/TREK_Ensign_<body>.x                    the posed mesh
    media/textures/TREK_Ensign_<body>_<division>.png       its atlas, x3

and the renders it was judged on into design/art/ensign/.

**Nothing here is modelled.** ENSIGN.md section 3 has the reasoning: a static
model cannot play an animation, but the game ships the animations *and* the
skinned bodies they drive, as text .x files. So this reads the vanilla male
or female body, the vanilla boilersuit rig our duty uniform already rides,
and a hairstyle, poses all three at one frame of the game's own
``Bob_SitGround_Pain_Stomach`` -- sitting on the ground, doubled over, a hand
on the stomach -- and bakes the result into one static mesh with one texture.
The figure is therefore exactly what the game would draw for a character in
that uniform in that pose, down to the proportions and the fold of the cloth,
and it is the same uniform the armoury issues, not a lookalike.

Run ``tools/gen_uniform.py`` first: the uniform quadrant of each atlas is the
generated duty texture, read from the mod's own textures folder, so a colour
change there reaches the ensign on the next run of this.

What the atlas holds, 512x512:

    +-----------+-----------+
    |   skin    |  uniform  |      each quadrant is a 256x256 source,
    +-----------+-----------+      copied in whole; the mesh's UVs are
    |   hair    |  boots    |      moved into its quadrant
    +-----------+-----------+
"""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import xskin
from import_gltf import _smooth_normals
from meshbuild import MeshBuilder
from pngwrite import Image, draw_text
from preview_model import read_png_rgba, render

PZ = r"C:\Program Files (x86)\Steam\steamapps\common\ProjectZomboid\media"
SKINNED = os.path.join(PZ, "models_X", "Skinned")
ANIMS = os.path.join(PZ, "anims_X", "Bob")
TEXTURES = os.path.join(PZ, "textures")

# The pose, and the moment of it. Sitting on the ground and doubled over reads
# as *hurt and alive*; the three lying-down poses the game has
# (Bob_Deadbody_OnBack, Bob_Idle_FloorOnFront, Bob_SitGround_SleepIdle) all
# read as a body, which is the one thing ROADMAP2 1.7 says the ensign must not look
# like. The frame is the middle of the loop, where the hand is on the stomach.
POSE = "Bob_SitGround_Pain_Stomach.x"
POSE_AT = 0.5

# Female bodies are driven by the same Bob animation, with every bone's
# *length* kept from the body's own skeleton: only the rotations are borrowed. The
# root is the exception -- its translation is where the pelvis sits above the
# ground, which is the pose, not the proportions.
ROOT_BONES = ("Dummy01", "Bip01", "Translation_Data")

BODIES = {
    "M": {
        "body": "MaleBody.x",
        "suit": os.path.join("Clothes", "Bob_BoilerSuit.X"),
        # Not CrewCut: that mesh is a cap over the front of the scalp and
        # leaves the back of the head bare, which a hunched pose shows
        # first. The render caught it; the source never would have.
        "hair": os.path.join("Hair", "Bob_Hair_Short.X"),
        "skin": os.path.join("Body", "MaleBody01.png"),
        "hair_colour": (74, 52, 36),
        "retarget": False,
    },
    "F": {
        "body": "FemaleBody.x",
        "suit": os.path.join("Clothes", "Kate_BoilerSuit.x"),
        "hair": os.path.join("Hair", "Kate_Hair_Bun.X"),
        "skin": os.path.join("Body", "FemaleBody01.png"),
        "hair_colour": (44, 32, 28),
        "retarget": True,
    },
}

DIVISIONS = ("command", "operations", "science")

# Which body triangles survive under the uniform. The duty uniform is a
# one-piece from collar to ankle and wrist, so of the body only the head, the
# neck above the collar and the hands show; everything else is inside the
# suit and would only poke through it at the joints the pose bends hardest.
SKIN_BONES = ("Bip01_Head", "Bip01_Neck", "Bip01_L_Hand", "Bip01_R_Hand",
              "Bip01_L_Finger0", "Bip01_L_Finger1", "Bip01_R_Finger0",
              "Bip01_R_Finger1")
# The feet are boots. They are the body's own feet, drawn from a flat dark
# quadrant: a shoe mesh is one more rig for the sake of a few pixels.
BOOT_BONES = ("Bip01_L_Foot", "Bip01_R_Foot", "Bip01_L_Toe0", "Bip01_R_Toe0")

BOOT = (26, 26, 30)
BOOT_SHINE = (46, 46, 54)

# The injury: a stain on the front of the uniform where the hand is. Placed
# by *bind-pose position* on the suit rig -- never by texel -- because an
# auto-packed atlas has no "front" (UNIFORMS.md: a texture painted in texture
# space will be wrong). The numbers are the rig's own: 0.98 tall, front at -Z.
BLOOD = (92, 14, 12)
WOUND_CENTRE = (0.035, 0.56)     # x, y on the rig
WOUND_RADIUS = 0.085

ATLAS = 512
QUAD = 256
QUADRANT = {"skin": (0, 0), "suit": (QUAD, 0), "hair": (0, QUAD),
            "boot": (QUAD, QUAD)}

PREVIEW_BG = (28, 30, 36)


def mesh_name(body):
    return "TREK_Ensign_" + body


def texture_name(body, division):
    return "TREK_Ensign_%s_%s" % (body, division.capitalize())


# ---------------------------------------------------------------------------
# Posing
# ---------------------------------------------------------------------------
def load(body):
    spec = BODIES[body]
    body_nodes = xskin.parse(os.path.join(SKINNED, spec["body"]))
    skeleton = xskin.Skeleton(body_nodes)
    anim = xskin.Animation(xskin.parse(os.path.join(ANIMS, POSE)))

    # **Measure the quaternion convention, do not assume it.** The body file
    # carries a short animation whose first key is its own frame pose, so
    # exactly one reading of the rotation keys reproduces the frame matrices.
    # A wrong reading throws nothing and bends every joint backwards.
    own = xskin.Animation(body_nodes)
    conjugate, plain, conj = xskin.quaternion_convention(skeleton, own)
    if conjugate is None:
        raise SystemExit("%s: neither quaternion reading reproduces the frame "
                         "matrices (%.4f / %.4f); refusing to guess"
                         % (spec["body"], plain, conj))

    keep = ()
    if spec["retarget"]:
        keep = tuple(b for b in skeleton.order if b not in ROOT_BONES)
    local = anim.local(skeleton, anim.length * POSE_AT, conjugate, keep)
    world = skeleton.world(local)

    parts = {
        "body": xskin.meshes(body_nodes)[0],
        "suit": xskin.meshes(xskin.parse(os.path.join(SKINNED, spec["suit"])))[0],
        "hair": xskin.meshes(xskin.parse(os.path.join(SKINNED, spec["hair"])))[0],
    }
    return spec, world, parts, conjugate


def build_mesh(body):
    """Returns (verts, faces, uvs, suit_bind) for one body in the pose.

    `suit_bind` maps each output vertex that came from the uniform to its
    position on the unposed rig, which is what the wound is painted by.
    """
    spec, world, parts, conjugate = load(body)
    verts, faces, uvs = [], [], []
    suit_bind = {}

    def quad_uv(uv, quadrant):
        ox, oy = QUADRANT[quadrant]
        u, v = uv
        # A rig's UVs sit in 0..1; wrap anything that does not, rather than
        # letting it bleed into the neighbouring quadrant.
        u, v = u % 1.0, v % 1.0
        return ((ox + u * QUAD) / ATLAS, (oy + v * QUAD) / ATLAS)

    def add(mesh, keep_face, quadrant_of_face, remember_bind=False):
        posed = mesh.skin(world)
        remap = {}
        for face in mesh.faces:
            if not keep_face(face):
                continue
            quadrant = quadrant_of_face(face)
            out = []
            for i in face:
                key = (i, quadrant)
                if key not in remap:
                    remap[key] = len(verts)
                    verts.append(posed[i])
                    uvs.append(quad_uv(mesh.uvs[i], quadrant))
                    if remember_bind:
                        suit_bind[remap[key]] = mesh.verts[i]
                out.append(remap[key])
            faces.append(tuple(out))

    bones = parts["body"].dominant_bones()
    visible = set(SKIN_BONES) | set(BOOT_BONES)
    add(parts["body"],
        lambda f: all(bones[i] in visible for i in f),
        lambda f: "boot" if any(bones[i] in BOOT_BONES for i in f) else "skin")
    add(parts["suit"], lambda f: True, lambda f: "suit", remember_bind=True)
    add(parts["hair"], lambda f: True, lambda f: "hair")

    # Sit the figure on the deck and on the middle of its square. The pose's own
    # origin is the character's, which is where the feet would be standing.
    ymin = min(v[1] for v in verts)
    xs = [v[0] for v in verts]
    zs = [v[2] for v in verts]
    cx, cz = (min(xs) + max(xs)) / 2, (min(zs) + max(zs)) / 2
    verts = [(x - cx, y - ymin, z - cz) for x, y, z in verts]
    return verts, faces, uvs, suit_bind, conjugate


# ---------------------------------------------------------------------------
# The atlas
# ---------------------------------------------------------------------------
def _blit(img, src_path, quadrant, tint=None):
    w, h, px = read_png_rgba(src_path)
    ox, oy = QUADRANT[quadrant]
    for y in range(QUAD):
        for x in range(QUAD):
            sx, sy = x * w // QUAD, y * h // QUAD
            i = (sy * w + sx) * 4
            r, g, b, a = px[i:i + 4]
            if tint:
                # Hair textures are white on purpose: the game tints them by
                # the character's hair colour, and a baked model has to do it
                # itself or every ensign is platinum blonde.
                r, g, b = (r * tint[0] // 255, g * tint[1] // 255,
                           b * tint[2] // 255)
            img.set(ox + x, oy + y, (r, g, b, 255 if a else 0))


def _boots(img):
    ox, oy = QUADRANT["boot"]
    for y in range(QUAD):
        for x in range(QUAD):
            # A faint diagonal sheen so the boots are leather and not a hole.
            c = BOOT_SHINE if (x + y) % 37 < 3 else BOOT
            img.set(ox + x, oy + y, c + (255,))


def _noise(x, y):
    """Deterministic value noise in 0..1, so every run paints the same stain."""
    n = int(x * 131) * 374761393 + int(y * 131) * 668265263
    n = (n ^ (n >> 13)) * 1274126177
    return ((n ^ (n >> 16)) & 0xFFFF) / 65535.0


def _wound(img, verts, faces, uvs, suit_bind):
    """Stains the uniform texels whose rig position is on the stomach, front."""
    painted = 0
    ox, oy = QUADRANT["suit"]
    for face in faces:
        if not all(i in suit_bind for i in face):
            continue
        bind = [suit_bind[i] for i in face]
        # Front of the rig is -Z. A stain that went through to the back
        # would be a bullet wound, and nobody asked for one of those.
        if min(p[2] for p in bind) > 0.02:
            continue
        pts = [(uvs[i][0] * ATLAS, uvs[i][1] * ATLAS) for i in face]
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        (x0, y0), (x1, y1), (x2, y2) = pts
        den = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        if abs(den) < 1e-9:
            continue
        for py in range(int(min(ys)), int(max(ys)) + 1):
            for px in range(int(min(xs)), int(max(xs)) + 1):
                if not (ox <= px < ox + QUAD and oy <= py < oy + QUAD):
                    continue
                a = ((y1 - y2) * (px + .5 - x2) + (x2 - x1) * (py + .5 - y2)) / den
                b = ((y2 - y0) * (px + .5 - x2) + (x0 - x2) * (py + .5 - y2)) / den
                c = 1 - a - b
                if min(a, b, c) < -0.02:
                    continue
                x = a * bind[0][0] + b * bind[1][0] + c * bind[2][0]
                y = a * bind[0][1] + b * bind[1][1] + c * bind[2][1]
                d = math.hypot((x - WOUND_CENTRE[0]) * 1.2, y - WOUND_CENTRE[1])
                edge = WOUND_RADIUS * (0.75 + 0.5 * _noise(x * 9, y * 9))
                if d > edge:
                    continue
                f = min(1.0, (edge - d) / (edge * 0.35)) * 0.85
                r, g, bb, al = img.get(px, py)
                img.set(px, py, (int(r + (BLOOD[0] - r) * f),
                                 int(g + (BLOOD[1] - g) * f),
                                 int(bb + (BLOOD[2] - bb) * f), al))
                painted += 1
    return painted


def build_atlas(body, division, uniform_dir, mesh):
    verts, faces, uvs, suit_bind = mesh
    spec = BODIES[body]
    img = Image(ATLAS, ATLAS, (0, 0, 0, 255))
    _blit(img, os.path.join(TEXTURES, spec["skin"]), "skin")
    _blit(img, os.path.join(uniform_dir, "duty_%s.png" % division), "suit")
    hair_tex = os.path.join(TEXTURES, "F_Hair_White.png")
    _blit(img, hair_tex, "hair", tint=spec["hair_colour"])
    _boots(img)
    painted = _wound(img, verts, faces, uvs, suit_bind)
    # A stain that covered nothing is a stain in the wrong place, and it is
    # the kind of fault that produces a perfectly plausible texture.
    if painted < 40:
        raise SystemExit("%s %s: the wound covered %d texels; the rig's "
                         "stomach is not where WOUND_CENTRE says"
                         % (body, division, painted))
    return img, painted


# ---------------------------------------------------------------------------
# Driving it
# ---------------------------------------------------------------------------
def build(root, art):
    media = os.path.join(root, "media")
    models = os.path.join(media, "models_X")
    textures = os.path.join(media, "textures")
    uniform_dir = os.path.join(textures, "clothes", "trek")
    os.makedirs(art, exist_ok=True)
    made = []
    for body in BODIES:
        verts, faces, uvs, suit_bind, conjugate = build_mesh(body)
        mb = MeshBuilder(up_axis="y")
        mb.verts = verts
        mb.faces = faces
        mb.uvs = uvs
        mb.norms = _smooth_normals(verts, faces)
        xpath = os.path.join(models, mesh_name(body) + ".x")
        nv, nf = mb.emit(xpath, mesh_name(body), texture_name(body, "command") + ".png")
        xs = [v[0] for v in verts]
        zs = [v[2] for v in verts]
        print("%s: %d vertices, %d faces, %.3f wide x %.3f deep x %.3f tall "
              "(quaternions %s)" % (mesh_name(body), nv, nf, max(xs) - min(xs),
                                    max(zs) - min(zs), max(v[1] for v in verts),
                                    "conjugated" if conjugate else "as stored"))
        for division in DIVISIONS:
            img, painted = build_atlas(body, division, uniform_dir,
                                       (verts, faces, uvs, suit_bind))
            tpath = os.path.join(textures, texture_name(body, division) + ".png")
            img.save(tpath)
            made.append((body, division, xpath, tpath))
            print("  %s: wound over %d texels" % (os.path.basename(tpath), painted))
    sheet(made, art)
    return made


def sheet(made, art):
    """Every ensign from two sides, on the preview background."""
    cell = 200
    scratch = os.path.join(art, "_render.png")
    rows = [("front", -35), ("back", 145)]
    img = Image(cell * len(made), cell * len(rows) + 16, PREVIEW_BG + (255,))
    for col, (body, division, xpath, tpath) in enumerate(made):
        draw_text(img, "%s %s" % (body, division[:3].upper()), col * cell + 6, 4,
                  (200, 200, 210, 255))
        for row, (_, yaw) in enumerate(rows):
            render(xpath, tpath, scratch, size=cell, yaw_deg=yaw)
            w, h, px = read_png_rgba(scratch)
            for y in range(h):
                for x in range(w):
                    i = (y * w + x) * 4
                    img.set(col * cell + x, 16 + row * cell + y,
                            tuple(px[i:i + 3]) + (255,))
    os.remove(scratch)
    out = os.path.join(art, "ensign_sheet.png")
    img.save(out)
    print("sheet ->", out)


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else os.path.join("TrekShuttle", "42")
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    build(root, os.path.join(here, "design", "art", "ensign"))
