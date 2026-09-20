"""Builds the bat'leth: mesh, in-hand texture, and nothing else.

    python tools/gen_batleth.py TrekShuttle/42

A bat'leth is a crescent held by grips on its *inner* edge, with four points:
a curving tip at each end and a spike part-way along each outer lobe. It is
drawn here as a flat ribbon of quads following an arc -- an outer edge, an
inner edge, a front and back face between them, and a rim joining the two --
because the shape is entirely a 2D silhouette given thickness, and building it
that way keeps every vertex on a curve that can be described in one line.

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
# long": 0.32 puts the bounding box at ~0.37, the widest a cross-body blade
# reads at before it starts wearing the character rather than the other way
# round. Real-world scale was never the test; the sprite is.
SPAN = 0.32
ARC = math.radians(78.0)        # half-angle swept by the crescent
THICK = 0.016                   # blade thickness, in metres
SEGMENTS = 96                   # samples along the arc

# The silhouette below was authored against a 0.46 m span in absolute metres,
# so every width is divided through by this and multiplied back by SPAN. Change
# SPAN alone without it and the crescent keeps its thickness while losing its
# reach -- a slender blade becomes a chunky one, which is a different weapon.
AUTHORED_SPAN = 0.46

# Texture regions: (x0, y0, x1, y1)
R_BLADE = (0, 0, 128, 40)       # polished steel, bright along the edge
R_RIM = (0, 40, 128, 56)        # the ground edge, lighter still
R_GRIP = (0, 56, 128, 88)       # wrapped leather on the inner edge
R_DARK = (0, 88, 128, 128)      # blued steel behind the grips

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


def profile(t):
    """Blade half-widths at arc parameter t in -1..1.

    Returns (outward, inward, is_grip). `outward` is the cutting edge, which
    carries the two lobes and their spikes; `inward` is the held edge, which
    is nearly straight and is where the hands go.
    """
    a = abs(t)

    # Taper to a point at both tips. Everything else is measured from a body
    # that is widest between the spike and the tip.
    tip = 1.0 if a < 0.86 else max(0.0, (1.0 - a) / 0.14)

    out = 0.052 + 0.030 * math.cos(math.pi * t)     # broad through the middle
    # The spikes: a narrow bump on each lobe, which is what stops the
    # silhouette reading as a plain crescent.
    spike = math.exp(-((a - 0.60) / 0.055) ** 2)
    out += 0.085 * spike
    out *= tip

    inn = 0.040 * tip

    # Every number above is in metres at AUTHORED_SPAN. Scaling them here keeps
    # the crescent's proportions whatever SPAN is set to.
    k = SPAN / AUTHORED_SPAN
    out *= k
    inn *= k

    # Three hand positions: one at the centre, one on each lobe inboard of the
    # spike. They are only a texture change -- cutting notches into the held
    # edge would weaken the silhouette at the size this is actually seen.
    is_grip = a < 0.13 or (0.30 < a < 0.46)
    return out, inn, is_grip


def build_mesh(path, texture_file):
    # MeshBuilder.place() maps (east, north, height) through whichever up-axis
    # the model wants, which is the right helper for something sitting on the
    # ground and the wrong one here: a blade has no "north". Going through it
    # authored the crescent lying flat with its thickness pointing at the sky,
    # which the preview caught immediately and no amount of reading the source
    # would have. So the vertices are written in the model's own axes, named:
    #
    #   X  across   tip to tip
    #   Y  depth    the height of the crescent -- Y is up for weapon meshes
    #   Z  thick    the flat of the blade
    #
    # which stands the blade up in its own plane, the way it is held.
    m = MeshBuilder(TEX_W, TEX_H, up_axis=UP_AXIS)

    def V(across, depth, thick):
        return (across, depth, thick)

    # Radius chosen so the chord between the two tips is SPAN.
    radius = (SPAN / 2.0) / math.sin(ARC)
    half = THICK / 2.0

    def edge(t):
        """Outer and inner edge points, in the blade plane, at parameter t."""
        ang = t * ARC
        out, inn, grip = profile(t)
        c, s = math.cos(ang), math.sin(ang)
        # x runs tip to tip, y is the depth of the crescent. Centred so the
        # middle grip sits on the origin, which is where the hand goes.
        cx, cy = radius * s, radius * c - radius
        return ((cx + out * s, cy + out * c),
                (cx - inn * s, cy - inn * c), grip)

    ts = [(-1.0 + 2.0 * i / SEGMENTS) for i in range(SEGMENTS + 1)]
    pts = [edge(t) for t in ts]

    for i in range(SEGMENTS):
        (o0, i0, g0), (o1, i1, g1) = pts[i], pts[i + 1]
        region = R_GRIP if (g0 and g1) else R_BLADE
        fu0, fu1 = (i / float(SEGMENTS)), ((i + 1) / float(SEGMENTS))

        # Front and back faces. Wound opposite ways so both are outward-facing;
        # MeshBuilder.quad maps its four points to fixed texture corners, so
        # the normal is passed explicitly rather than inferred from winding --
        # reversing the points to turn a face around also turns its artwork
        # over, which is what put the shuttle's registry on upside down.
        m.quad(V(o0[0], o0[1], half), V(o1[0], o1[1], half),
               V(i1[0], i1[1], half), V(i0[0], i0[1], half),
               region, V(0, 0, 1))
        m.quad(V(i0[0], i0[1], -half), V(i1[0], i1[1], -half),
               V(o1[0], o1[1], -half), V(o0[0], o0[1], -half),
               region, V(0, 0, -1))

        # The cutting edge and the held edge, as rims of THICK depth.
        ox, oy = o1[0] - o0[0], o1[1] - o0[1]
        ln = math.hypot(ox, oy) or 1.0
        nrm = V(oy / ln, -ox / ln, 0)
        m.quad(V(o0[0], o0[1], -half), V(o1[0], o1[1], -half),
               V(o1[0], o1[1], half), V(o0[0], o0[1], half), R_RIM, nrm)
        ix, iy = i1[0] - i0[0], i1[1] - i0[1]
        ln = math.hypot(ix, iy) or 1.0
        nrm = V(-iy / ln, ix / ln, 0)
        m.quad(V(i0[0], i0[1], half), V(i1[0], i1[1], half),
               V(i1[0], i1[1], -half), V(i0[0], i0[1], -half),
               R_RIM if not (g0 and g1) else R_GRIP, nrm)

    nv, nf = m.emit(path, "TREKBatleth", texture_file)

    # The number that actually matters is not SPAN but the bounding box the
    # engine sees: the arc bulges past its own chord, and it was that gap
    # (0.46 asked for, 0.531 drawn) that made the blade read oversized while
    # the constant said it was in vanilla's bracket. Report it, and compare it
    # with the widest weapon vanilla ships.
    xs = [p for (o, i, _) in pts for p in (o[0], i[0])]
    ys = [p for (o, i, _) in pts for p in (o[1], i[1])]
    bbox = (max(xs) - min(xs), max(ys) - min(ys), THICK)
    return nv, nf, radius, bbox


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


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else "TrekShuttle/42"
    mesh_dir = os.path.join(root, "media", "models_X", "weapons", "2handed")
    tex_dir = os.path.join(root, "media", "textures", "weapons", "2handed")
    os.makedirs(mesh_dir, exist_ok=True)
    os.makedirs(tex_dir, exist_ok=True)

    tex = os.path.join(tex_dir, "TREK_Batleth.png")
    mesh = os.path.join(mesh_dir, "TREK_Batleth.x")
    build_texture(tex)
    nv, nf, radius, bbox = build_mesh(mesh, "TREK_Batleth.png")
    print(f"bat'leth: {nv} verts, {nf} faces, span {SPAN} m, arc radius "
          f"{radius:.3f} m")
    print(f"  bbox    {bbox[0]:.3f} across x {bbox[1]:.3f} deep x "
          f"{bbox[2]:.3f} thick  (vanilla's widest weapon mesh is the canoe "
          f"paddle at 0.123 across; a machete is 0.335 long)")
    print(f"  mesh    {mesh}")
    print(f"  texture {tex}")
    build_icon(mesh, tex,
               os.path.join(root, "media", "textures", "Item_TREK_Batleth.png"))
