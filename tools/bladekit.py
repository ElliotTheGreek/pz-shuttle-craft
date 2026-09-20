"""Shared machinery for the mod's bladed weapons.

The bat'leth was built first and alone, and `gen_batleth.py` still carries its
own copy of all of this because its crescent is genuinely a different problem
-- an arc, authored in polar coordinates. The mek'leth, lirpa and ushaan-tor
are all the *same* problem: a flat silhouette running up the Y axis, given
thickness. So that part lives here rather than three times over.

What a caller supplies is a **section list**, bottom to top:

    (y, xl, xr, face_region, edge_region)

one cross-section of the blade at height `y`, running from `xl` to `xr` across.
Consecutive sections are joined into front and back faces and the two rims.
Asymmetric profiles are the point: a single-edged sword is a thick spine on one
side and a ground edge on the other, and that is just `xl` and `xr` moving
independently.

Three rules every weapon here inherits, each of which cost something once:

  * **Y is up.** Vanilla weapon meshes are Y-up; the hull and the helm are
    Z-up. This is the opposite of every other mesh in the repo.
  * **The mesh's own dimensions are its size in game.** `WeaponLength` is a
    reach stat and scales nothing. `tools/meshbbox.py` measures what the engine
    will actually see -- ours and vanilla's -- and the bracket to sit in is a
    measurement, not a remembered number.
  * **Judge the bounding box, not the constant you set.** A curved edge bulges
    past its own chord. The bat'leth asked for 0.46 and drew 0.531.

The model block for anything built with this must be declared in `module Base`
(`media/scripts/trekweapons.txt`), never in the mod's own module -- see the
comment at the top of that file. The item stays in `module TrekShuttle`.
"""
import math
import os

from meshbuild import MeshBuilder
from pngwrite import Image

TEX_W = TEX_H = 128
UP_AXIS = "y"

# Texture strips, shared so the four weapons read as one armoury.
R_BLADE = (0, 0, 128, 40)       # polished steel, bright along the edge
R_EDGE = (0, 40, 128, 56)       # the ground edge, lighter still
R_GRIP = (0, 56, 128, 88)       # wrapped leather
R_DARK = (0, 88, 128, 128)      # blued steel, and the shaft

STEEL = (188, 196, 204, 255)
STEEL_LIT = (232, 238, 244, 255)
STEEL_DARK = (96, 104, 114, 255)
BLUED = (48, 54, 64, 255)
GRIP = (58, 40, 28, 255)
GRIP_LIT = (92, 66, 46, 255)
BRASS = (150, 118, 58, 255)
WOOD = (96, 70, 44, 255)
WOOD_LIT = (132, 100, 66, 255)
# Gunmetal, for a part that is *structurally* dark but has to survive being
# drawn at 32px on PZ's near-black inventory panel. BLUED is (48,54,64) on a
# (39,39,39) background and simply disappears -- which is how the lirpa's
# counterweight, the one feature that identifies the weapon, vanished from its
# own icon. Same failure as the bloodwine bottle in DEV_GUIDE.
GUNMETAL = (108, 116, 128, 255)
GUNMETAL_LIT = (146, 154, 166, 255)


def build_texture(path, shaft=None):
    """The shared four-strip sheet.

    `shaft` recolours the **dark** strip: "wood" for a pole, "gunmetal" for a
    part that must stay dark in the fiction and still be visible at 32px on a
    near-black inventory panel. Recolouring a shared region affects everything
    using it, which is worth remembering -- an early lirpa asked for a wooden
    shaft and turned its steel counterweight into timber, because both were on
    R_DARK.
    """
    img = Image(TEX_W, TEX_H, BLUED)

    # Blade: a bright line along the cutting edge falling off to shadow at the
    # spine. At the size a weapon is drawn in hand, that gradient is the only
    # thing that says "sharpened" rather than "flat grey plank".
    x0, y0, x1, y1 = R_BLADE
    img.rect(x0, y0, x1, y1, STEEL)
    img.rect(x0, y0, x1, y0 + 6, STEEL_LIT)
    img.rect(x0, y1 - 8, x1, y1, STEEL_DARK)
    for i in range(x0, x1, 16):          # faint forging bands
        img.rect(i, y0 + 8, i + 1, y1 - 9, STEEL_DARK)

    x0, y0, x1, y1 = R_EDGE
    img.rect(x0, y0, x1, y1, STEEL_LIT)

    # Grips: wrapped leather with brass ferrules at both ends.
    x0, y0, x1, y1 = R_GRIP
    img.rect(x0, y0, x1, y1, GRIP)
    for i in range(x0, x1, 8):
        img.rect(i, y0, i + 4, y1, GRIP_LIT)
    img.rect(x0, y0, x1, y0 + 3, BRASS)
    img.rect(x0, y1 - 3, x1, y1, BRASS)

    x0, y0, x1, y1 = R_DARK
    if shaft == "wood":
        img.rect(x0, y0, x1, y1, WOOD)
        for i in range(x0, x1, 11):      # grain, so a pole is not a bar
            img.rect(i, y0, i + 2, y1, WOOD_LIT)
    elif shaft == "gunmetal":
        img.rect(x0, y0, x1, y1, GUNMETAL)
        img.rect(x0, y0, x1, y0 + 5, GUNMETAL_LIT)
        img.rect(x0, y1 - 6, x1, y1, BLUED)
    else:
        img.rect(x0, y0, x1, y1, BLUED)
    img.save(path)
    return path


def flat_blade(m, sections, thick):
    """Extrudes a section list into front, back and both rims.

    Returns the bounding box of the silhouette, which is the number worth
    reading -- see the module docstring.
    """
    half = thick / 2.0

    def V(across, up, through):
        # Named, because MeshBuilder.place() maps (east, north, height) and is
        # the wrong helper for a blade: a blade has no "north". Going through
        # it once authored the bat'leth lying flat with its thickness pointing
        # at the sky, which a render caught in one look and the source never
        # would have.
        #   X  across the blade
        #   Y  up its length -- Y is up for weapon meshes
        #   Z  through its thickness
        return (across, up, through)

    for a, b in zip(sections, sections[1:]):
        ya, xla, xra, facea, edgea = a
        yb, xlb, xrb, faceb, edgeb = b
        face = facea if facea == faceb else R_BLADE

        # Front and back. Wound opposite ways so both face outward; the normal
        # is passed explicitly rather than inferred, because MeshBuilder.quad
        # maps its four points to fixed texture corners and reversing them to
        # turn a face around also turns its artwork over.
        m.quad(V(xla, ya, half), V(xra, ya, half),
               V(xrb, yb, half), V(xlb, yb, half), face, V(0, 0, 1))
        m.quad(V(xlb, yb, -half), V(xrb, yb, -half),
               V(xra, ya, -half), V(xla, ya, -half), face, V(0, 0, -1))

        # The two rims, each given an outward normal in the blade's plane.
        edge = edgea if edgea == edgeb else R_EDGE
        dx, dy = xrb - xra, yb - ya
        ln = math.hypot(dx, dy) or 1.0
        m.quad(V(xra, ya, -half), V(xrb, yb, -half),
               V(xrb, yb, half), V(xra, ya, half), edge, V(dy / ln, -dx / ln, 0))
        dx, dy = xlb - xla, yb - ya
        ln = math.hypot(dx, dy) or 1.0
        m.quad(V(xla, ya, half), V(xlb, yb, half),
               V(xlb, yb, -half), V(xla, ya, -half), edge, V(-dy / ln, dx / ln, 0))

    # Cap the bottom, so a pommel is not an open tube seen from below.
    y, xl, xr, _, edge = sections[0]
    m.quad(V(xl, y, -half), V(xr, y, -half), V(xr, y, half), V(xl, y, half),
           edge, V(0, -1, 0))

    xs = [v for s in sections for v in (s[1], s[2])]
    ys = [s[0] for s in sections]
    return (max(xs) - min(xs), max(ys) - min(ys), thick)


def bar(m, y0, y1, half_w, half_d, region):
    """A square-section length of shaft or haft, y0 to y1.

    Four sides only. A round pole would be more faces for a shape that is two
    pixels wide in the sprite, and every vanilla shaft is a box too.
    """
    def V(a, u, t):
        return (a, u, t)
    w, d = half_w, half_d
    for (nx, nz, p0, p1) in (
        (0, 1, (-w, d), (w, d)),
        (0, -1, (w, -d), (-w, -d)),
        (1, 0, (w, d), (w, -d)),
        (-1, 0, (-w, -d), (-w, d)),
    ):
        (ax, az), (bx, bz) = p0, p1
        m.quad(V(ax, y0, az), V(bx, y0, bz), V(bx, y1, bz), V(ax, y1, az),
               region, V(nx, 0, nz))


def icon_from_mesh(mesh_path, tex_path, out, render_size=512, icon=32,
                   margin=0.10, tilt=0.0):
    """Renders the inventory icon from the mesh this tool just built.

    The win is not only that it is easier than describing a Klingon blade to an
    image model -- two goes at the bat'leth produced a curved sword with a hilt
    and then a featureless arch. It is that the icon is then the **same object**
    as the in-hand model, from the same mesh and texture, so the two cannot
    drift apart.

    `preview_model` draws on a flat (28, 30, 36) with no antialiasing, so the
    background is keyed by **exact match**, never with `key_icon.py`'s colour
    ramp: grip leather is only 33 away from that backdrop, well inside what the
    ramp treats as "probably background", and the hand bindings would be keyed
    away.

    **32x32, and that is not a style choice.** Every one of these items has an
    `AttachmentType`, which makes it the kind vanilla's hotbar draws, and
    `ISHotbar.lua:52` places it at `slotX + tex:getWidth() / 2` -- the slot's
    left edge plus *half the texture's own width*, which only centres when the
    texture is half the 60px slot. A 64px icon starts at the middle of its own
    slot and runs 36px into the next one. `tests/test_assets.py` enforces it.

    `tilt` is for a weapon wider than it is tall; a vertical blade wants 0.
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


def emit(root, name, mesh_name, sections=None, thick=0.012, extra=None,
         shaft=None, tilt=0.0, hand="1handed", note="", parts=None):
    """Builds texture, mesh and icon for one weapon and reports its size.

    `sections` is one silhouette; `parts` is several, for a weapon that is not
    one continuous flat shape -- the lirpa is a blade at one end and a weight
    at the other with a pole between, and running those as a single section
    list would web the gaps over with quads.

    `extra(m)` is called afterwards, for anything a flat silhouette cannot
    express at all: the lirpa's shaft is a square bar, because a pole rendered
    as a flat ribbon is a pole seen edge-on from half the angles.
    """
    mesh_dir = os.path.join(root, "media", "models_X", "weapons", hand)
    tex_dir = os.path.join(root, "media", "textures", "weapons", hand)
    os.makedirs(mesh_dir, exist_ok=True)
    os.makedirs(tex_dir, exist_ok=True)

    tex = os.path.join(tex_dir, name + ".png")
    mesh = os.path.join(mesh_dir, name + ".x")
    build_texture(tex, shaft=shaft)

    m = MeshBuilder(TEX_W, TEX_H, up_axis=UP_AXIS)
    groups = parts if parts else ([sections] if sections else [])
    boxes = [flat_blade(m, g, thick) for g in groups]
    if boxes:
        # Across and thick are the widest of any part; long is measured over
        # all of them together, because a lirpa's length is pommel to tip and
        # no single part carries it.
        lo = min(s[0] for g in groups for s in g)
        hi = max(s[0] for g in groups for s in g)
        box = (max(b[0] for b in boxes), hi - lo, max(b[2] for b in boxes))
    else:
        box = (0, 0, thick)
    if extra:
        extra(m)
    nv, nf = m.emit(mesh, mesh_name, name + ".png")

    print(f"{note or name}: {nv} verts, {nf} faces")
    print(f"  bbox    {box[0]:.3f} across x {box[1]:.3f} long x "
          f"{box[2]:.3f} thick   (silhouette only; run tools/meshbbox.py on "
          f"the file for the whole mesh)")
    print(f"  mesh    {mesh}")
    print(f"  texture {tex}")
    icon_from_mesh(mesh, tex,
                   os.path.join(root, "media", "textures",
                                "Item_" + name + ".png"), tilt=tilt)
    return mesh, tex
